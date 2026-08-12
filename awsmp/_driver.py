import csv
import logging
import re
from typing import IO, Any, Dict, List, NoReturn, Optional, Tuple, cast

import boto3
from botocore.exceptions import ClientError

from . import changesets, models
from .errors import (
    AccessDeniedException,
    AmiPriceChangeError,
    AmiPricingModelChangeError,
    MarketplaceAPIException,
    MissingInstanceTypeError,
    NoVersionException,
    ResourceInUseException,
    ResourceNotFoundException,
    ServiceQuotaExceededException,
    ThrottlingException,
    UnrecognizedClientException,
    ValidationException,
)
from .types import ChangeSetReturnType, ChangeSetType

logger = logging.getLogger(__name__)


class AmiProduct:
    def __init__(self, product_id: str, dry_run: bool = False):
        self.product_id: str = product_id
        self.offer_id = get_public_offer_id(product_id)
        self._dry_run = dry_run

    @staticmethod
    def create(dry_run: bool):
        changeset = changesets.get_ami_listing_creation_changesets()
        changeset_name = "Create new AMI Product"

        return get_response(changeset, changeset_name, dry_run)

    def update_legal_terms(self, eula_document: Dict[str, str]) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_legal_terms_changesets(eula_document, self.offer_id)
        changeset_name = f"Product {self.product_id} legal terms update"

        return get_response(changeset, changeset_name, self._dry_run)

    def update_support_terms(self, refund_policy: str) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_support_terms_changesets(self.offer_id, refund_policy)
        changeset_name = f"Product {self.product_id} support terms update"

        return get_response(changeset, changeset_name, self._dry_run)

    def update_description(self, desc: Dict) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_description_changesets(self.product_id, desc)
        changeset_name = f"Product {self.product_id} description update"

        return get_response(changeset, changeset_name, self._dry_run)

    def update_instance_types(
        self, offer_config: Dict[str, Any], price_change_allowed: bool
    ) -> Optional[ChangeSetReturnType]:
        """
        Update instance types and pricing term based on the offer config
        :param Dict[str, Any] offer_config: offer configuration loaded from yaml file
        :param bool price_change_allowed: flag to indicate price change is allowed
        :return: Changeset for updating instance API request or None
        :rtype: ChangeSetReturnType or None
        """

        changeset, hourly_diff, annual_diff = self._get_instance_type_changeset_and_pricing_diff(
            offer_config, price_change_allowed
        )
        changeset_name = f"Product {self.product_id} instance type update"

        if changeset is None:
            return None

        return get_response(changeset, changeset_name, self._dry_run)

    def update_regions(self, region_config: Dict) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_region_changesets(self.product_id, region_config)
        changeset_name = f"Product {self.product_id} region update"

        return get_response(changeset, changeset_name, self._dry_run)

    def update_version(self, version_config: Dict) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_version_changesets(self.product_id, version_config)
        changeset_name = f"Product {self.product_id} version update"

        return get_response(changeset, changeset_name, self._dry_run)

    def release(self) -> ChangeSetReturnType:
        changeset = changesets.get_ami_release_changesets(self.product_id, self.offer_id)
        changeset_name = f"Product {self.product_id} publish as limited"

        return get_response(changeset, changeset_name, self._dry_run)

    def update(self, configs: Dict[str, Any], price_change_allowed: bool) -> Optional[ChangeSetReturnType]:
        """
        Update AMI product details (Description, Region, Instance type), public offer pricing terms, and
        support terms based on the given configuration file.
        :param configs dict[str, Any]: Local configuration file
        :param bool price_change_allowed: Flag to indicate price change is allowed
        :return: Response from the request
        :rtype: ChangeSetReturnType
        """
        changeset = changesets.get_ami_listing_update_changesets(
            self.product_id, configs["product"]["description"], configs["product"]["region"]
        )

        changeset_pricing, hourly_diff, annual_diff = self._get_instance_type_changeset_and_pricing_diff(
            configs["offer"], price_change_allowed
        )

        if hourly_diff or annual_diff:
            if not price_change_allowed:
                logger.error(
                    "There are pricing changes but changing price flag is not set. Please check the pricing files or set the price flag.\nPrice change details:\nHourly: %s\nAnnual: %s\n"
                    % (hourly_diff, annual_diff)
                )
                return None

        if changeset_pricing is not None:
            changeset.extend(changeset_pricing)

        refund_policy = configs["offer"]["refund_policy"]
        changeset_support = changesets.get_ami_listing_update_support_terms_changesets(self.offer_id, refund_policy)
        changeset.extend(changeset_support)

        changeset_name = f"Product {self.product_id} update product details"

        return get_response(changeset, changeset_name, self._dry_run)

    def _get_product_title(self):
        return get_entity_details(self.product_id)["Description"]["ProductTitle"]

    def _get_instance_type_changeset_and_pricing_diff(
        self, offer_config: Dict[str, Any], price_change_allowed: bool
    ) -> Tuple[Optional[List[ChangeSetType]], List, List]:
        """
        Get the instance type and pricing term changeset and pricing diffs
        :param offer_config Dict[str, Any]: offer configuration loaded from yaml file
        :return: Set of changesets, hourly pricing differences and annual pricing differences
        :rtype: Tuple[Optional[List[ChangeSetType]], List, List]
        """
        offer_detail = models.Offer(**offer_config)

        local_instance_types = {instance_type.name for instance_type in offer_detail.instance_types}
        # Currently-active dimensions the listing has (from the product's Dimensions field), plus
        # the subset currently restricted (inactive). Restricted instance types are excluded from
        # Dimensions.
        existing_instance_types, restricted_instance_types = _get_existing_and_restricted_instance_types(
            self.product_id
        )

        new_instance_types = list(local_instance_types - existing_instance_types)
        # Previously restricted types that local config wants active again. The dimension already
        # exists, so only AddInstanceTypes is required (no AddDimensions).
        reenabled_instance_types = list(local_instance_types & restricted_instance_types)
        # Currently-active types dropped from local config: these must be newly restricted in this
        # batch. Types already restricted from a prior update must not be resubmitted to
        # RestrictInstanceTypes/RestrictDimensions.
        removed_instance_types = list((existing_instance_types - local_instance_types) - restricted_instance_types)

        # The new UpdatePricingTerms rate card must be built by *modifying* the existing offer rate
        # card, not by rebuilding it from local config alone:
        #   - Only dimensions being restricted/removed in THIS change set batch may be dropped.
        #   - Dimensions already restricted from a PRIOR update must keep their existing price -
        #     AWS rejects a rate card that silently drops rates for dimensions it still considers
        #     part of the "existing rate card" with
        #     "INVALID_RATE_CARD: Rates can't be removed from UsageBasedPricingTerm."
        #   - Conversely, a dimension being restricted/removed in this same batch must NOT keep a
        #     price - AWS rejects that with "INCOMPATIBLE_PRODUCT: Use existing, available
        #     dimensions in the product in UsageBasedPricingTerm."
        # local_instance_types (new/reenabled/unchanged-active) get their price from local config;
        # every other pre-existing dimension not being removed this batch (e.g. an already-restricted
        # type the operator isn't touching) is carried over unchanged from the existing rate card.
        existing_terms = get_entity_details(self.offer_id)["Terms"]
        existing_hourly, existing_annual = _get_full_ratecard_info(existing_terms)
        preserved_rate_card_hourly = [
            entry
            for entry in existing_hourly
            if entry["DimensionKey"] not in local_instance_types and entry["DimensionKey"] not in removed_instance_types
        ]
        preserved_rate_card_annual = [
            entry
            for entry in existing_annual
            if entry["DimensionKey"] not in local_instance_types and entry["DimensionKey"] not in removed_instance_types
        ]

        changeset = changesets.get_ami_listing_update_instance_type_changesets(
            self.product_id,
            self.offer_id,
            offer_detail,
            new_instance_types,
            removed_instance_types,
            reenabled_instance_types=reenabled_instance_types,
            preserved_rate_card_hourly=preserved_rate_card_hourly,
            preserved_rate_card_annual=preserved_rate_card_annual,
        )

        # Safety net: every dimension the listing will still have after this update (locally
        # configured types, plus any still-restricted types the operator isn't touching) must have
        # a price in the rate card. This guards against the existing offer rate card being stale or
        # incomplete relative to the product entity, which would otherwise surface as an opaque AWS
        # rejection ("Rates can't be removed from UsageBasedPricingTerm").
        still_restricted_instance_types = restricted_instance_types - set(reenabled_instance_types)
        _validate_pricing_terms_dimension_coverage(
            changeset, expected_instance_types=local_instance_types | still_restricted_instance_types
        )

        hourly_diff, annual_diff = _get_pricing_diff(self.product_id, changeset, price_change_allowed)

        if not hourly_diff and not annual_diff:
            if not new_instance_types and not removed_instance_types and not reenabled_instance_types:
                # There are nothing to update
                logger.info("There is no instance information details to update.")
                return None, [], []

        return changeset, hourly_diff, annual_diff


def get_ib_client():
    """Return a boto3 imagebuilder client pinned to us-east-1."""
    return boto3.client("imagebuilder", region_name="us-east-1")


class IbProduct:
    """Driver for EC2 Image Builder component products."""

    def __init__(self, product_id: str, dry_run: bool = False):
        self.product_id: str = product_id
        self._dry_run = dry_run

    def publish_component(self, component: models.IBComponent) -> str:
        """Create an IB component via imagebuilder.create_component or return existing ARN.

        In dry-run mode, prints the would-be payload and returns a placeholder ARN.
        """
        if component.arn is not None:
            logger.info("Using pre-existing component ARN: %s", component.arn)
            return component.arn

        params: dict[str, Any] = {
            "name": component.name,
            "semanticVersion": component.semantic_version,
            "platform": component.platform,
            "description": component.description or "",
            "data": component.document,
        }
        if component.supported_os_versions:
            params["supportedOsVersions"] = component.supported_os_versions

        if self._dry_run:
            logger.warning("DRY_RUN: imagebuilder.create_component(%s)", params)
            return "arn:aws:imagebuilder:us-east-1:123456789012:component/dry-run/1.0.0/1"

        try:
            response = get_ib_client().create_component(**params)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
                match = re.search(r"(arn:aws[^'\"\s]+)", e.response["Error"]["Message"])
                if match is None:
                    _raise_client_error(e)
                arn = match.group(1)
                logger.debug("Component already exists, continuing with ARN: %s", arn)
                return arn
            _raise_client_error(e)

        arn = response["componentBuildVersionArn"]
        logger.info("Created component: %s", arn)
        return arn

    def publish_components(self, ib_product: models.IBProduct) -> list[str]:
        """Create/resolve ARNs for all delivery options in order."""
        return [self.publish_component(opt.component) for opt in ib_product.version.delivery_options]

    def add_version(self, ib_product: models.IBProduct) -> ChangeSetReturnType:
        """Full pipeline: create components then submit AddDeliveryOptions."""
        component_arns = self.publish_components(ib_product)
        changeset = changesets.get_ib_listing_add_version_changesets(self.product_id, ib_product, component_arns)
        changeset_name = f"Product {self.product_id} IB add version"
        return get_response(changeset, changeset_name, self._dry_run)

    def restrict_version(self, delivery_option_ids: list[str]) -> ChangeSetReturnType:
        """Submit RestrictDeliveryOptions changeset."""
        changeset = changesets.get_ib_listing_restrict_version_changesets(self.product_id, delivery_option_ids)
        changeset_name = f"Product {self.product_id} IB restrict version"
        return get_response(changeset, changeset_name, self._dry_run)


def get_client(service_name="marketplace-catalog", region_name="us-east-1"):
    return boto3.client(service_name, region_name=region_name)


def get_response(changeset: List[ChangeSetType], changeset_name: str, dry_run: bool = False) -> ChangeSetReturnType:
    """
    Request to AWS and get response of either success of failure

    :param List[ChangeSetType] changeset: list of changesets
    :param str changeset_name: name of changeset
    :param bool dry_run: should actions be dry_run
    :return: changeset with type, entity, details etc.
    :rtype: ChangeSetReturnType
    """
    changeset_name = changeset_name.replace(",", "_").replace("(", "").replace(")", "")
    logger.info(
        "Requesting changes to marketplace listing", extra={"ChangeSetName": changeset_name, "ChangeSet": changeset}
    )
    if dry_run:
        logger.warning("DRY_RUN: %s", changeset)
        return {
            "ChangeSetArn": "DRY_RUN",
            "ChangeSetId": "DRY_RUN",
        }
    try:
        response = get_client().start_change_set(
            Catalog="AWSMarketplace",
            ChangeSet=changeset,
            ChangeSetName=changeset_name,
        )
    except ClientError as e:
        _raise_client_error(e)

    return response


def _raise_client_error(exception: ClientError) -> NoReturn:
    exception_code, error_msg = exception.response["Error"]["Code"], exception.response["Error"]["Message"]
    if exception_code == "AccessDeniedException":
        logger.exception(f"Profile does not have marketplace access. Please check your profile role or services.")
        raise AccessDeniedException(service_name="marketplace")
    elif exception_code == "UnrecognizedClientException":
        logger.exception(f"Profile is not configured correctly. Please check your credential with associated profile.")
        raise UnrecognizedClientException from None
    elif exception_code == "ResourceNotFoundException":
        logger.exception(f"Product/Offer ID does not exist. Please check IDs and try again.")
        raise ResourceNotFoundException from None
    elif exception_code == "ValidationException":
        logger.exception(f"Please check schema regex and request with fixed value.")
        raise ValidationException(error_msg) from None
    elif exception_code == "ResourceInUseException":
        logger.exception(error_msg)
        raise ResourceInUseException(error_msg) from None
    elif exception_code == "ServiceQuotaExceededException":
        logger.exception(error_msg)
        raise ServiceQuotaExceededException(error_msg) from None
    elif exception_code == "ThrottlingException":
        logger.exception(error_msg)
        raise ThrottlingException(error_msg) from None
    else:
        logger.exception(error_msg)
        raise MarketplaceAPIException(exception_code, error_msg) from None


def list_entities(entity_type: str) -> dict[str, dict[str, str]]:
    client = get_client()
    entities = dict()
    paginator = client.get_paginator("list_entities")
    page_iterator = paginator.paginate(
        Catalog="AWSMarketplace",
        EntityType=entity_type,
    )
    for page in page_iterator:
        for e in page["EntitySummaryList"]:
            entities[e["EntityId"]] = e
    return entities


def get_entities_by_visibility(entity_type: str, visibilities: tuple[models.AmiVisibility, ...]) -> list[dict]:
    """
    Return entity summaries for the given entity_type filtered by Marketplace Visibility.

    :param str entity_type: Marketplace entity type, e.g. "Offer" or "AmiProduct"
    :param tuple[Visibility, ...] visibilities: One or more Visibility enum values to include
    :return: A list of entity summary dicts as returned by ListEntities
    :rtype: list[dict]
    """
    entities = list_entities(entity_type)
    return [e for e in entities.values() if not visibilities or e["Visibility"] in visibilities]


def get_entity_details(entity_id: str) -> Dict:
    client = get_client()
    try:
        e = client.describe_entity(Catalog="AWSMarketplace", EntityId=entity_id)
    except ClientError as error:
        _raise_client_error(error)

    return e["DetailsDocument"]


def get_ami_product_version_summary() -> list[models.AmiProductVersionSummary]:
    """
    Query a list each marketplace entry with its number of versions.
    """
    entity_dict = list_entities("AmiProduct")
    versions = [
        models.AmiProductVersionSummary(entity_id, len(get_entity_versions(entity_id)), entity_dict[entity_id]["Name"])
        for entity_id in entity_dict.keys()
    ]
    return versions


def get_public_offer_id(entity_id: str):
    client = get_client()
    e = client.list_entities(
        Catalog="AWSMarketplace",
        EntityType="Offer",
        EntityTypeFilters={
            "OfferFilters": {
                "ProductId": {
                    "ValueList": [
                        entity_id,
                    ]
                },
                "Targeting": {"ValueList": ["None"]},
            }
        },
    )
    if not e["EntitySummaryList"]:
        raise ResourceNotFoundException(f"\n\nOffer with entity-id {entity_id} not found.\n")

    return e["EntitySummaryList"][0]["EntityId"]


def get_entity_versions(entity_id: str) -> List[dict[str, str]]:
    details = get_entity_details(entity_id)
    if "Versions" not in details.keys():
        return []
    return sorted(details["Versions"], key=lambda x: x["CreationDate"])


def _get_ratecard_info(changeset: Dict, idx: int, instance_types: List[str]) -> List[Dict]:
    ratecard = changeset[3]["DetailsDocument"]["Terms"][idx]["RateCards"][0]["RateCard"]
    return [r for r in ratecard if r["DimensionKey"] in instance_types]


def _get_full_ratecard_info(terms: List) -> Tuple[List, List]:
    """
    Get the full ratecard information from Terms
    :param List terms: Terms details from the entity or changeset details
    :return two lists of hourly or/and annual rate cards
    :rtype: Tuple[List, List]
    """
    hourly, annual = [], []
    for term in terms:
        if term["Type"] == "UsageBasedPricingTerm":
            hourly = term["RateCards"][0]["RateCard"]
        elif term["Type"] == "ConfigurableUpfrontPricingTerm":
            annual = term["RateCards"][0]["RateCard"]

    return hourly, annual


def _validate_pricing_terms_dimension_coverage(
    changeset: List[ChangeSetType], expected_instance_types: set[str]
) -> None:
    """
    Verify the UpdatePricingTerms rate card in the changeset covers every expected dimension.

    Safety net for the invariant that every instance type dimension the listing will still have
    after an update (locally configured, or still restricted and untouched this batch) must have a
    price defined. This does not re-derive which dimensions are expected - the caller is
    responsible for that - it only guards against the existing offer rate card being stale or
    incomplete relative to the product entity, which would otherwise surface as an opaque AWS
    rejection ("Rates can't be removed from UsageBasedPricingTerm").

    :param List[ChangeSetType] changeset: changeset produced for the update
    :param set expected_instance_types: instance types that must be priced
    :raises MissingInstanceTypeError: if the rate card is missing pricing for any expected type
    """
    change = cast(dict[str, Any], changeset[0])
    terms = change["DetailsDocument"]["Terms"]
    hourly, _annual = _get_full_ratecard_info(terms)
    priced_instance_types = {r["DimensionKey"] for r in hourly}

    if missing := expected_instance_types - priced_instance_types:
        raise MissingInstanceTypeError(list(missing))


def _build_pricing_diff(existing_prices: List, local_prices: List) -> List:
    """
    Compare prices of each instance types and return difference details
    :param List existing_prices: price information from existing/live listing
    :param List local_prices: price information from local configuration file
    :return: List of different pricing information for an instance type
    :rtype: List
    """
    original_pricing, local_pricing = {}, {}
    if existing_prices:
        original_pricing = {price["DimensionKey"]: price["Price"] for price in existing_prices}
    if local_prices:
        local_pricing = {price["DimensionKey"]: price["Price"] for price in local_prices}

    diffs = []
    for key in original_pricing:
        if key in local_pricing and float(original_pricing[key]) != float(local_pricing[key]):
            diffs.append(
                {"DimensionKey": key, "Original Price": original_pricing[key], "New Price": local_pricing[key]}
            )

    return diffs


def _get_pricing_diff(product_id: str, changeset: List[ChangeSetType], allow_price_update: bool) -> Tuple[List, List]:
    """
    Check if there are differences between the given changeset from the local configuration and the existing listing pricing terms
    :param str product_id: product id of existing/live listing
    :param List[ChangeSetType] chageset: changeset from local configuration file
    :return: Hourly and Anuual pricing diff details
    :rtype: Tuple[List, List]
    """
    change = cast(dict[str, Any], changeset[0])
    local_details_document = change["DetailsDocument"]
    local_pricing_changesets = local_details_document["Terms"]
    local_hourly, local_annual = _get_full_ratecard_info(local_pricing_changesets)

    # existing pricing information from the listing
    existing_listing_status = get_entity_details(product_id)["Description"]["Visibility"]
    existing_terms = get_entity_details(get_public_offer_id(product_id))["Terms"]
    existing_hourly, existing_annual = _get_full_ratecard_info(existing_terms)

    diffs_hourly = _build_pricing_diff(existing_hourly, local_hourly)
    diffs_annual = _build_pricing_diff(existing_annual, local_annual)

    def _has_different_pricing_model():
        return models.Offer.get_offer_type_from_offer_terms(
            local_pricing_changesets
        ) != models.Offer.get_offer_type_from_offer_terms(existing_terms)

    if existing_listing_status == "Restricted":
        # This refers to the overall listing's Visibility (private/restricted-audience listing),
        # which is a separate concept from Compatibility.RestrictedInstanceTypes (per-instance-type
        # restriction handled in _get_instance_type_changeset_and_pricing_diff). A listing with
        # restricted Visibility does not support updating instance types at all.
        error_message = "Restricted listings may not have instance types updated."
        raise AmiPriceChangeError(error_message)
    elif existing_listing_status != "Draft" and _has_different_pricing_model():
        raise AmiPricingModelChangeError("Listing is published. Contact AWS Marketplace to change the pricing type.")

    existing_hourly, existing_annual = _get_full_ratecard_info(existing_terms)

    def any_zero_to_paid(diffs):
        # check if pricing request from free (0.0) to non-zero prices
        return bool(diffs) and any(
            float(item["Original Price"]) == 0.0 and float(item["New Price"]) != 0.0 for item in diffs
        )

    instance_configuration_changed = any(
        [local_annual and not existing_annual, existing_annual and not local_annual, diffs_annual, diffs_hourly]
    )

    if (any_zero_to_paid(diffs_hourly) or any_zero_to_paid(diffs_annual)) and not allow_price_update:
        error_msg = f"""Free product was attempted to be converted to paid product.
            Please check the pricing files or set the price flag.\n
            Price change details:\n
            Local pricing updates: {local_annual}\nExisting pricing in local: {existing_annual}\n"
            """
        logger.error(error_msg)
        raise AmiPriceChangeError(error_msg)

    elif instance_configuration_changed and not allow_price_update:
        error_message = f"""There are pricing changes in either hourly or annual prices.
        Please check the pricing files or allow price change.
        Price change details:\n
        Local pricing updates: {local_annual}\nExisting pricing in local: {existing_annual}\n"
        """
        logger.error(error_message)
        raise AmiPriceChangeError(error_message)

    return diffs_hourly, diffs_annual


def build_pricing_rows_from_offer(offer_id: str, *, free: bool = False) -> list[tuple[str, str, str]]:
    """
    Return [(instance_type, hourly, annual)] based on an existing offer.
    """
    e = get_client().describe_entity(Catalog="AWSMarketplace", EntityId=offer_id)
    details = e["DetailsDocument"]

    prices_hourly = {}
    prices_annual = {}
    for term in details["Terms"]:
        if term["Type"] not in ["UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"]:
            continue
        for rate_card in term["RateCards"]:
            for d in rate_card["RateCard"]:
                if term["Type"] == "UsageBasedPricingTerm":
                    # hourly
                    prices_hourly[d["DimensionKey"]] = d["Price"]
                elif term["Type"] == "ConfigurableUpfrontPricingTerm":
                    # annual
                    prices_annual[d["DimensionKey"]] = d["Price"]
                else:
                    raise Exception(f'Unknown terms type {term["type"]}')

    # both should have the same keys so calculate the symmetric difference
    # this should never happen given that we get the data from an available offer
    # free listing can be skipped since it doesn't have annual pricing
    if not free:
        if prices_hourly.keys() ^ prices_annual.keys():
            raise Exception("instance type dimensions are not identical in hourly and annual prices")
    else:
        prices_annual = prices_hourly

    return [(it, prices_hourly[it], prices_annual[it]) for it in sorted(prices_hourly.keys())]


def _get_existing_instance_types(product_id: str):
    entity = get_entity_details(product_id)
    # New created product does not have existing instance types
    existing_instance_types = set()
    if "Dimensions" in entity:
        existing_instance_types = {t["Name"] for t in entity["Dimensions"]}
    return existing_instance_types


def _get_existing_and_restricted_instance_types(product_id: str) -> Tuple[set[str], set[str]]:
    """
    Return the active dimensions the listing currently has, plus the subset currently restricted.

    Combines both extractions into a single describe_entity call. Note that the returned
    "existing" set (from the product's Dimensions field) does NOT include currently-restricted
    instance types.

    These sets drive which instance types get RestrictInstanceTypes/RestrictDimensions calls, but
    they must NOT be used to decide what stays priced in UpdatePricingTerms: pricing must be derived
    from the existing offer rate card (see _get_instance_type_changeset_and_pricing_diff) since a
    dimension already restricted from a prior update must keep its existing price, while a
    dimension newly restricted/removed in this same batch must have its price dropped.

    :param str product_id: product id
    :return: Tuple of (active existing instance types, currently restricted instance types)
    :rtype: Tuple[set[str], set[str]]
    """
    entity = get_entity_details(product_id)
    existing_instance_types: set[str] = set()
    if "Dimensions" in entity:
        existing_instance_types = {t["Name"] for t in entity["Dimensions"]}
    return existing_instance_types, _extract_restricted_instance_types(entity)


def _extract_restricted_instance_types(entity: Dict) -> set[str]:
    """
    Extract the set of currently-restricted instance types from an entity/product details document.

    Restricted instance types are excluded from the product's Dimensions list in
    describe_entity output, even though the underlying rate card dimension (and its price) is
    still present on the offer. AWS requires that dimension keep its price if it was restricted in
    a prior update (removing it triggers "INVALID_RATE_CARD: Rates can't be removed from
    UsageBasedPricingTerm"), but rejects a price for it if it is being restricted in this same
    change-set batch ("INCOMPATIBLE_PRODUCT: Use existing, available dimensions"). Compatibility.
    RestrictedInstanceTypes is the only place these types can be discovered from the product entity.

    :param Dict entity: entity details document (as returned by describe_entity)
    :return: Set of instance type names currently restricted
    :rtype: set[str]
    """
    restricted_instance_types: set[str] = set()
    compatibility = entity.get("Compatibility")
    if isinstance(compatibility, dict):
        restricted = compatibility.get("RestrictedInstanceTypes")
        if isinstance(restricted, list):
            restricted_instance_types = set(restricted)
    return restricted_instance_types


def get_available_instance_types(arch: str, virt: str) -> list[str]:
    """
    Return available EC2 instance types for the given arch/virt.
    """
    client = get_client(service_name="ec2")
    try:
        e = client.get_instance_types_from_instance_requirements(
            ArchitectureTypes=[arch],
            VirtualizationTypes=[virt],
            InstanceRequirements={
                "VCpuCount": {
                    "Min": 0,
                },
                "MemoryMiB": {
                    "Min": 0,
                },
            },
        )
    except ClientError:
        logger.exception("Profile does not have EC2 service access. Check your profile role or services.")
        raise AccessDeniedException(service_name="ec2")

    available_instances = [i["InstanceType"] for i in e["InstanceTypes"]]

    return available_instances


def _filter_instance_types(product_id: str, changeset, hourly=False):
    existing_instance_types = _get_existing_instance_types(product_id)
    pricing_instance_types = {
        t["DimensionKey"] for t in changeset[3]["DetailsDocument"]["Terms"][0]["RateCards"][0]["RateCard"]
    }

    if missing_instance_types := existing_instance_types.difference(pricing_instance_types):
        logger.exception(f"Instance types does not match with original listing.")
        raise MissingInstanceTypeError(missing_instance_types)
    intersect = list(pricing_instance_types.intersection(existing_instance_types))

    # idx 0 is hourly pricing, and 1 is annual
    indexes = {0} if hourly else {0, 1}
    for idx in indexes:
        changeset[3]["DetailsDocument"]["Terms"][idx]["RateCards"][0]["RateCard"] = _get_ratecard_info(
            changeset, idx, intersect
        )
    return changeset


def offer_create(
    product_id: str,
    buyer_accounts: list[str],
    available_for_days: int,
    valid_for_days: int,
    offer_name: str,
    eula_url: Optional[str],
    pricing: IO,
    dry_run: bool,
    hourly: bool = False,
) -> ChangeSetReturnType:
    csvreader = csv.DictReader(pricing, fieldnames=["name", "price_hourly", "price_annual"])
    instance_type_pricing = [models.InstanceTypePricing(**line) for line in csvreader]  # type: ignore

    if hourly:
        for i in instance_type_pricing:
            i.price_annual = None

    if eula_url:
        eula_document = {"type": "CustomEula", "url": eula_url}
    else:
        eula_document = {"type": "StandardEula", "version": "2022-07-14"}

    changeset_list = changesets.get_changesets(
        product_id,
        offer_name,
        buyer_accounts,
        instance_type_pricing,
        available_for_days,
        valid_for_days + available_for_days + 1,
        eula_document,
    )

    changeset_list = _filter_instance_types(product_id, changeset_list, hourly=hourly)

    changeset_name = f'{f"create private offer for {product_id}: {offer_name}"[:95]}...'

    return get_response(changeset_list, changeset_name, dry_run)


def create_offer_name(product_id: str, buyer_accounts: List[str], with_support: bool, customer_name: str) -> str:
    details = get_entity_details(product_id)

    account_part = ",".join(buyer_accounts)
    if len(account_part) > 50:
        account_part = f"{account_part[:47]}..."
    title_part = details["Description"]["ProductTitle"]
    support_part = " wSupport" if with_support else ""

    return f"Offer - {account_part} - {title_part}{support_part} - {customer_name}"[:150]


def get_full_response(product_id: str) -> dict[str, Any]:
    """
    Return the full response details from `entity_describe` output

    :param dict[str, Any] product_id: Product id of the listing
    :return: Dictionary of response details
    :rtype: dict
    """

    listing_resp = get_entity_details(product_id)
    # keep the only latest version
    if "Versions" in listing_resp:
        if listing_resp["Versions"]:
            listing_resp["Versions"] = listing_resp["Versions"][-1]
        else:
            raise NoVersionException("Version information is empty. No version details are available.")
    else:
        raise NoVersionException("Version is not found. Listing does not have version information")

    offer_id = get_public_offer_id(product_id)
    listing_offer_resp = get_entity_details(offer_id)

    # filtering required term details only
    listing_resp["Terms"] = []
    term_order = {"SupportTerm": 0, "UsageBasedPricingTerm": 1, "ConfigurableUpfrontPricingTerm": 2}
    if "Terms" in listing_offer_resp:
        listing_resp["Terms"] = sorted(
            [term for term in listing_offer_resp.get("Terms", []) if term["Type"] in term_order],
            key=lambda x: term_order.get(x["Type"], 3),
        )
    return listing_resp


def diff_entity_id_vs_local(entity_id: str, local_entity: models.EntityModel):
    """
    Fetch live by id, compare against provided local model.
    """

    full_response = get_full_response(entity_id)
    restricted_instance_types = _extract_restricted_instance_types(full_response)

    entity_from_listing = models.EntityModel(**full_response)
    diff = entity_from_listing.get_diff(local_entity, restricted_instance_types=restricted_instance_types)

    return diff
