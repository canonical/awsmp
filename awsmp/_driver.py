import csv
import logging
from typing import IO, Any, Dict, List, Literal, Optional

import boto3
from botocore.exceptions import ClientError

from . import changesets, models
from .errors import (
    AccessDeniedException,
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
        self, offer_config: Dict[str, Any], dimension_unit: Literal["Hrs", "Units"]
    ) -> ChangeSetReturnType:
        """
        Update instance types and pricing term based on the offer config
        :param Dict[str, Any] offer_config: offer configuration loaded from yaml file
        :param Literal["Hrs", "Units"] dimension_unit: Either hourly or units
        :return: Changeset for updating instance API request
        :rtype: ChangeSetReturnType
        """
        offer_detail = models.Offer(**offer_config)

        all_instance_types = {instance_type.name for instance_type in offer_detail.instance_types}
        existing_instance_types = _get_existing_instance_types(self.product_id)
        new_instance_types = list(all_instance_types - existing_instance_types)

        changeset = changesets.get_ami_listing_update_instance_type_changesets(
            self.product_id, self.offer_id, offer_detail, dimension_unit, new_instance_types
        )
        changeset_name = f"Product {self.product_id} instance type update"

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

    def update(self, configs: dict[str, Any]) -> ChangeSetReturnType:
        """
        Update AMI product details (Description, Region)
        """
        changeset = changesets.get_ami_listing_update_changesets(
            self.product_id, configs["product"]["description"], configs["product"]["region"]
        )
        changeset_name = f"Product {self.product_id} update product details"

        return get_response(changeset, changeset_name)

    def _get_product_title(self):
        return get_entity_details(self.product_id)["Description"]["ProductTitle"]


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
