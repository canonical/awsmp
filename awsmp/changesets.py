import datetime
import json
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

import boto3
from pydantic import BaseModel, Field, HttpUrl, conlist, field_validator
from typing_extensions import NotRequired

from awsmp.constants import CATEGORIES

from . import models
from .types import ChangeSetType, UpdateDimensionChange


def _changeset_create_offer(product_id: str, offer_name: str) -> ChangeSetType:
    return {
        "ChangeType": "CreateOffer",
        "ChangeName": "CreateOfferChange",
        "Entity": {"Type": "Offer@1.0"},
        "DetailsDocument": {
            "ProductId": product_id,
        },
    }


def _changeset_create_ami_product() -> ChangeSetType:
    return {
        "ChangeType": "CreateProduct",
        "ChangeName": "CreateProductChange",
        "Entity": {"Type": "AmiProduct@1.0"},
        "DetailsDocument": {},
    }


def _changeset_update_information(
    offer_name: str,
    offer_id: str = "$CreateOfferChange.Entity.Identifier",
) -> ChangeSetType:
    return {
        "ChangeType": "UpdateInformation",
        "Entity": {"Type": "Offer@1.0", "Identifier": offer_id},
        "DetailsDocument": {
            "Name": offer_name,
            "Description": "testing automatic offer creation",
        },
    }


def _changeset_update_targeting(buyer_accounts: List[str]) -> ChangeSetType:
    return {
        "ChangeType": "UpdateTargeting",
        "Entity": {"Type": "Offer@1.0", "Identifier": "$CreateOfferChange.Entity.Identifier"},
        "DetailsDocument": {"PositiveTargeting": {"BuyerAccounts": buyer_accounts}},
    }


def _changeset_update_pricing_terms(
    instance_type_pricing: List[models.InstanceTypePricing],
    offer_id: Optional[str] = None,
) -> ChangeSetType:
    rate_cards_hourly: List[Dict[str, str]] = []
    rate_cards_annual: List[Dict[str, str]] = []

    # set offer_id for combined call for private offer creation
    if not offer_id:
        offer_id = "$CreateOfferChange.Entity.Identifier"

    # generate the rate cards
    for instance_type_price in instance_type_pricing:
        # Free public listing is 0.00 which is false
        if instance_type_price.price_hourly is not None:
            rate_cards_hourly.append(
                {
                    "DimensionKey": instance_type_price.name,
                    "Price": str(instance_type_price.price_hourly),
                }
            )

        if instance_type_price.price_annual is not None:
            rate_cards_annual.append(
                {
                    "DimensionKey": instance_type_price.name,
                    "Price": str(instance_type_price.price_annual),
                }
            )

    # hourly rate card are required for both public/private offer
    terms = [
        {
            "Type": "UsageBasedPricingTerm",
            "CurrencyCode": "USD",
            "RateCards": [{"RateCard": rate_cards_hourly}],
        },
    ]

    if rate_cards_annual:
        terms.append(
            {
                "Type": "ConfigurableUpfrontPricingTerm",
                "CurrencyCode": "USD",
                "RateCards": [
                    {
                        "Selector": {
                            "Type": "Duration",
                            "Value": "P365D",
                        },
                        "Constraints": {
                            "MultipleDimensionSelection": "Allowed",
                            "QuantityConfiguration": "Allowed",
                        },
                        "RateCard": rate_cards_annual,
                    }
                ],
            },
        )

    # the changeset part
    return {
        "ChangeType": "UpdatePricingTerms",
        "Entity": {"Type": "Offer@1.0", "Identifier": offer_id},
        "DetailsDocument": {"PricingModel": "Usage", "Terms": terms},
    }


def _changeset_update_availability(days_from_today: int) -> ChangeSetType:
    end = datetime.date.today() + datetime.timedelta(days=days_from_today)
    return {
        "ChangeType": "UpdateAvailability",
        "Entity": {
            "Type": "Offer@1.0",
            "Identifier": "$CreateOfferChange.Entity.Identifier",
        },
        "DetailsDocument": {"AvailabilityEndDate": end.strftime("%Y-%m-%d")},
    }


def _changeset_update_legal_terms(eula_document: Dict[str, str], offer_id: Optional[str] = None) -> ChangeSetType:
    eula = models.EulaDocumentItem(**eula_document)  # type: ignore

    eula_changeset: dict[str, str] = {"Type": eula.type}
    if eula.url is not None:
        eula_changeset["Url"] = eula.url
    elif eula.version is not None:
        eula_changeset["Version"] = eula.version

    if not offer_id:
        offer_id = "$CreateOfferChange.Entity.Identifier"

    return {
        "ChangeType": "UpdateLegalTerms",
        "Entity": {"Type": "Offer@1.0", "Identifier": offer_id},
        "DetailsDocument": {"Terms": [{"Type": "LegalTerm", "Documents": [eula_changeset]}]},
    }


def _changeset_update_validity_terms(days: int) -> ChangeSetType:
    return {
        "ChangeType": "UpdateValidityTerms",
        "Entity": {"Type": "Offer@1.0", "Identifier": "$CreateOfferChange.Entity.Identifier"},
        "DetailsDocument": {"Terms": [{"Type": "ValidityTerm", "AgreementDuration": f"P{days}D"}]},
    }


def _changeset_release_offer(offer_id: Optional[str] = None) -> ChangeSetType:
    if not offer_id:
        offer_id = "$CreateOfferChange.Entity.Identifier"
    return {
        "ChangeType": "ReleaseOffer",
        "Entity": {
            "Type": "Offer@1.0",
            "Identifier": offer_id,
        },
        "DetailsDocument": {},
    }


def _changeset_update_support_terms(refund_policy: str, offer_id: Optional[str] = None) -> ChangeSetType:
    if not offer_id:
        offer_id = "$CreateOfferChange.Entity.Identifier"
    return {
        "ChangeType": "UpdateSupportTerms",
        "Entity": {
            "Type": "Offer@1.0",
            "Identifier": offer_id,
        },
        "DetailsDocument": {
            "Terms": [
                {
                    "Type": "SupportTerm",
                    "RefundPolicy": refund_policy,
                }
            ]
        },
    }


def _changeset_update_ami_product_description(product_id: str, desc: Dict) -> ChangeSetType:
    # description data format checking
    m = models.Description(**desc)

    # return changeset
    return {
        "ChangeType": "UpdateInformation",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": {
            "ProductTitle": desc["product_title"],
            "LogoUrl": desc["logourl"],
            "ShortDescription": desc["short_description"],
            "LongDescription": m.long_description,
            "Highlights": desc["highlights"],
            "SearchKeywords": desc["search_keywords"],
            "Categories": desc["categories"],
            "Sku": desc["sku"],
            "AdditionalResources": m.additional_resources,
            "VideoUrls": desc["video_urls"],
            "SupportDescription": m.support_description,
        },
    }


def _changeset_update_ami_product_instance_type(product_id: str, new_instance_types: List[str]) -> ChangeSetType:
    # return changeset
    return {
        "ChangeType": "AddInstanceTypes",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": {"InstanceTypes": new_instance_types},
    }


def _changeset_update_ami_product_region(product_id: str, region_config: Dict) -> ChangeSetType:
    # config file format checking available regions
    regions = models.Region(**region_config)

    # return changeset
    return {
        "ChangeType": "AddRegions",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": {"Regions": regions.commercial_regions},
    }


def _changeset_update_ami_product_future_region(product_id: str, region_config: Dict) -> ChangeSetType:
    region = models.Region(**region_config)
    # return changeset
    return {
        "ChangeType": "UpdateFutureRegionSupport",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": {"FutureRegionSupport": {"SupportedRegions": region.future_region_supported()}},
    }


def _build_metered_instance_unit(instance_type: str, dimension_unit: Literal["Hrs", "Units"]) -> UpdateDimensionChange:
    return {
        "Description": instance_type,
        "Key": instance_type,
        "Name": instance_type,
        "Types": [
            "Metered",
        ],
        "Unit": dimension_unit,
    }


def _changeset_update_ami_product_dimension(
    product_id: str, dimension_unit: Literal["Hrs", "Units"], new_instance_types: List[str]
):
    # generate dimension list
    dimension_changeset: List[UpdateDimensionChange] = [
        _build_metered_instance_unit(instance_type, dimension_unit) for instance_type in new_instance_types
    ]

    return {
        "ChangeType": "AddDimensions",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": dimension_changeset,
    }


def _changeset_update_ami_product_version(product_id: str, version_config: Dict) -> ChangeSetType:
    version = models.AmiVersion(**version_config)
    # return changeset
    return {
        "ChangeType": "AddDeliveryOptions",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": {
            "Version": {
                "VersionTitle": version.version_title,
                "ReleaseNotes": version.release_notes,
            },
            "DeliveryOptions": [
                {
                    "Details": {
                        "AmiDeliveryOptionDetails": {
                            "AmiSource": {
                                "AmiId": version.ami_id,
                                "AccessRoleArn": version.access_role_arn,
                                "UserName": version.os_user_name,
                                "OperatingSystemName": version.os_system_name,
                                "OperatingSystemVersion": version.os_system_version,
                                "ScanningPort": version.scanning_port,
                            },
                            "UsageInstructions": version.usage_instructions,
                            "RecommendedInstanceType": version.recommended_instance_type,
                            "SecurityGroups": [
                                {
                                    "IpProtocol": version.ip_protocol,
                                    "IpRanges": version.ip_ranges,
                                    "FromPort": version.from_port,
                                    "ToPort": version.to_port,
                                }
                            ],
                        }
                    }
                }
            ],
        },
    }


def _changeset_release_ami_product(product_id: str) -> ChangeSetType:
    return {
        "ChangeType": "ReleaseProduct",
        "Entity": {
            "Type": "AmiProduct@1.0",
            "Identifier": product_id,
        },
        "DetailsDocument": {},
    }


def get_changesets(
    product_id: str,
    offer_name: str,
    buyer_accounts: List[str],
    instance_type_pricing: List[models.InstanceTypePricing],
    available_for_days: int,
    valid_for_days: int,
    eula_document: Dict[str, str],
) -> List[ChangeSetType]:
    return [
        _changeset_create_offer(product_id, offer_name),
        _changeset_update_information(offer_name),
        _changeset_update_targeting(buyer_accounts),
        _changeset_update_pricing_terms(instance_type_pricing),
        _changeset_update_availability(available_for_days),
        _changeset_update_legal_terms(eula_document),
        _changeset_update_validity_terms(valid_for_days),
        _changeset_release_offer(),
    ]


def get_ami_listing_creation_changesets() -> List[ChangeSetType]:
    return [
        _changeset_create_ami_product(),
        _changeset_create_offer("$CreateProductChange.Entity.Identifier", "Public Offer creation"),
    ]


def get_ami_listing_update_description_changesets(product_id: str, description: Dict) -> List[ChangeSetType]:
    return [
        _changeset_update_ami_product_description(product_id, description),
    ]


def get_ami_listing_update_instance_type_changesets(
    product_id: str,
    offer_id: str,
    instance_type_pricing: List[models.InstanceTypePricing],
    dimension_unit: Literal["Hrs", "Units"],
    new_instance_types: List[str],
) -> List[ChangeSetType]:
    return [
        _changeset_update_ami_product_dimension(product_id, dimension_unit, new_instance_types),
        _changeset_update_ami_product_instance_type(product_id, new_instance_types),
        _changeset_update_pricing_terms(instance_type_pricing, offer_id=offer_id),
    ]


def get_ami_listing_update_region_changesets(product_id: str, region_config: Dict) -> List[ChangeSetType]:
    return [
        _changeset_update_ami_product_region(product_id, region_config),
        _changeset_update_ami_product_future_region(product_id, region_config),
    ]


def get_ami_listing_update_version_changesets(product_id: str, version_config: Dict) -> List[ChangeSetType]:
    return [
        _changeset_update_ami_product_version(product_id, version_config),
    ]


def get_ami_listing_update_legal_terms_changesets(eula_document: Dict[str, str], offer_id: str) -> List[ChangeSetType]:
    return [
        _changeset_update_legal_terms(eula_document, offer_id=offer_id),
    ]


def get_ami_listing_update_support_terms_changesets(offer_id: str, refund_policy: str) -> List[ChangeSetType]:
    return [
        _changeset_update_support_terms(refund_policy, offer_id=offer_id),
    ]


def get_ami_release_changesets(product_id: str, offer_id: str) -> List[ChangeSetType]:
    return [
        _changeset_release_ami_product(product_id),
        _changeset_update_information(f"Product id {product_id} public offer", offer_id),
        _changeset_release_offer(offer_id=offer_id),
    ]


def get_ami_listing_update_changesets(product_id: str, description: dict, region_config: dict) -> List[ChangeSetType]:
    return [
        _changeset_update_ami_product_description(product_id, description),
        _changeset_update_ami_product_region(product_id, region_config),
        _changeset_update_ami_product_future_region(product_id, region_config),
    ]
