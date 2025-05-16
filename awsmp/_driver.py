import csv
import logging
from typing import IO, Any, Dict, List, Optional, Tuple, cast

import boto3
from botocore.exceptions import ClientError

from . import changesets, models
from .errors import (
    AccessDeniedException,
    AmiPriceChangeError,
    MissingInstanceTypeError,
    ResourceNotFoundException,
    UnrecognizedClientException,
    ValidationException,
)
from .types import ChangeSetReturnType, ChangeSetType

logger = logging.getLogger(__name__)


class AmiProduct:
    def __init__(self, product_id: str):
        self.product_id: str = product_id
        self.offer_id = get_public_offer_id(product_id)

    @staticmethod
    def create():
        changeset = changesets.get_ami_listing_creation_changesets()
        changeset_name = "Create new AMI Product"

        return get_response(changeset, changeset_name)

    def update_legal_terms(self, eula_document: Dict[str, str]) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_legal_terms_changesets(eula_document, self.offer_id)
        changeset_name = f"Product {self.product_id} legal terms update"

        return get_response(changeset, changeset_name)

    def update_support_terms(self, refund_policy: str) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_support_terms_changesets(self.offer_id, refund_policy)
        changeset_name = f"Product {self.product_id} support terms update"

        return get_response(changeset, changeset_name)

    def update_description(self, desc: Dict) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_description_changesets(self.product_id, desc)
        changeset_name = f"Product {self.product_id} description update"

        return get_response(changeset, changeset_name)

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

        return get_response(changeset, changeset_name)

    def update_regions(self, region_config: Dict) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_region_changesets(self.product_id, region_config)
        changeset_name = f"Product {self.product_id} region update"

        return get_response(changeset, changeset_name)

    def update_version(self, version_config: Dict) -> ChangeSetReturnType:
        changeset = changesets.get_ami_listing_update_version_changesets(self.product_id, version_config)
        changeset_name = f"Product {self.product_id} version update"

        return get_response(changeset, changeset_name)

    def release(self) -> ChangeSetReturnType:
        changeset = changesets.get_ami_release_changesets(self.product_id, self.offer_id)
        changeset_name = f"Product {self.product_id} publish as limited"

        return get_response(changeset, changeset_name)

    def update(self, configs: Dict[str, Any], price_change_allowed: bool) -> Optional[ChangeSetReturnType]:
        """
        Update AMI product details (Description, Region, Instance type) and public offer pricing term
        :prarm configs dict[str, Any]: Local configuration file
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
        elif not changeset_pricing:
            return None

        if changeset_pricing is not None:
            changeset.extend(changeset_pricing)

        changeset_name = f"Product {self.product_id} update product details"

        return get_response(changeset, changeset_name)

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
        existing_instance_types = _get_existing_instance_types(self.product_id)
        new_instance_types = list(local_instance_types - existing_instance_types)
        removed_instance_types = list(existing_instance_types - local_instance_types)

        changeset = changesets.get_ami_listing_update_instance_type_changesets(
            self.product_id, self.offer_id, offer_detail, new_instance_types, removed_instance_types
        )

        hourly_diff, annual_diff = _get_pricing_diff(self.product_id, changeset, price_change_allowed)

        if not hourly_diff and not annual_diff:
            if not new_instance_types and not removed_instance_types:
                # There are nothing to update
                logger.info("There is no instance information details to update.")
                return None, [], []

        return changeset, hourly_diff, annual_diff


def get_client(service_name="marketplace-catalog", region_name="us-east-1"):
    return boto3.client(service_name, region_name=region_name)


def get_response(changeset: List[ChangeSetType], changeset_name: str) -> ChangeSetReturnType:
    """
    Request to AWS and get response of either success of failure

    :param List[ChangeSetType] changeset: list of changesets
    :param str changeset_name: name of changeset
    :return: changeset with type, entity, details etc.
    :rtype: ChangeSetReturnType
    """
    changeset_name = changeset_name.replace(",", "_").replace("(", "").replace(")", "")
    try:
        response = get_client().start_change_set(
            Catalog="AWSMarketplace",
            ChangeSet=changeset,
            ChangeSetName=changeset_name,
        )
    except ClientError as e:
        _raise_client_error(e)

    return response


def _raise_client_error(exception: ClientError):
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
    else:
        logger.exception(error_msg)
        raise Exception


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


def get_entity_details(entity_id: str) -> Dict:
    client = get_client()
    try:
        e = client.describe_entity(Catalog="AWSMarketplace", EntityId=entity_id)
    except ClientError as error:
        _raise_client_error(error)

    return e["DetailsDocument"]


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
    local_pricing_changesets = change["DetailsDocument"]["Terms"]
    local_hourly, local_annual = _get_full_ratecard_info(local_pricing_changesets)

    # existing pricing information from the listing
    existing_listing_status = get_entity_details(product_id)["Description"]["Visibility"]
    existing_terms = get_entity_details(get_public_offer_id(product_id))["Terms"]
    existing_hourly, existing_annual = _get_full_ratecard_info(existing_terms)

    diffs_hourly = _build_pricing_diff(existing_hourly, local_hourly)
    diffs_annual = _build_pricing_diff(existing_annual, local_annual)

    if existing_listing_status == "Restricted":
        # restricted instances do not support updating instance types
        error_message = "Restricted listings may not have instance types updated."
        raise AmiPriceChangeError(error_message)

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
            Local pricing updates: {local_annual}\Existing pricing in local: {existing_annual}\n"
            """
        logger.error(error_msg)
        raise AmiPriceChangeError(error_msg)
    elif instance_configuration_changed and not allow_price_update:
        error_message = f"""There are pricing changes in either hourly or annual prices.
        Please check the pricing files or allow price change.
        Price change details:\n
        Local pricing updates: {local_annual}\Existing pricing in local: {existing_annual}\n"
        """
        logger.error(error_message)
        raise AmiPriceChangeError(error_message)

    return diffs_hourly, diffs_annual


def _get_existing_instance_types(product_id: str):
    entity = get_entity_details(product_id)
    # New created product does not have existing instance types
    existing_instance_types = set()
    if "Dimensions" in entity:
        existing_instance_types = {t["Name"] for t in entity["Dimensions"]}
    return existing_instance_types


def _filter_instance_types(product_id: str, changeset):
    existing_instance_types = _get_existing_instance_types(product_id)
    pricing_instance_types = {
        t["DimensionKey"] for t in changeset[3]["DetailsDocument"]["Terms"][0]["RateCards"][0]["RateCard"]
    }

    if missing_instance_types := existing_instance_types.difference(pricing_instance_types):
        logger.exception(f"Instance types does not match with original listing.")
        raise MissingInstanceTypeError(missing_instance_types)
    intersect = list(pricing_instance_types.intersection(existing_instance_types))

    # idx 0 is hourly pricing, and 1 is annual
    for idx in {0, 1}:
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
) -> ChangeSetReturnType:
    csvreader = csv.DictReader(pricing, fieldnames=["name", "price_hourly", "price_annual"])
    instance_type_pricing = [models.InstanceTypePricing(**line) for line in csvreader]  # type:ignore

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

    changeset_list = _filter_instance_types(product_id, changeset_list)

    changeset_name = f'{f"create private offer for {product_id}: {offer_name}"[:95]}...'

    return get_response(changeset_list, changeset_name)


def create_offer_name(product_id: str, buyer_accounts: List[str], with_support: bool, customer_name: str) -> str:
    details = get_entity_details(product_id)

    account_part = ",".join(buyer_accounts)
    if len(account_part) > 50:
        account_part = f"{account_part[:47]}..."
    title_part = details["Description"]["ProductTitle"]
    support_part = " wSupport" if with_support else ""

    return f"Offer - {account_part} - {title_part}{support_part} - {customer_name}"[:150]
