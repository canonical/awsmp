from __future__ import annotations

import json
from decimal import Decimal
from enum import Enum
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    TypedDict,
    Union,
)

import boto3
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    HttpUrl,
    StrictStr,
    conlist,
    constr,
    field_validator,
    model_validator,
)

from .constants import CATEGORIES
from .yaml_utils import LiteralString


class InstanceTypePricing(BaseModel):
    name: str
    price_hourly: Annotated[Decimal, Field(alias="hourly", ge=0.00)]
    price_annual: Annotated[Optional[Decimal], Field(alias="yearly", default=None, ge=0.00)]

    class Config:
        populate_by_name = True

    @model_validator(mode="after")
    def check_decimal_precision(cls, values):
        # Check price_hourly
        if values.price_hourly is not None:
            if len(str(values.price_hourly).split(".")[-1]) > 3:
                raise ValueError(f"price_hourly must have at most 3 decimal places, got {values.price_hourly}")

        # Check price_annual
        if values.price_annual is not None:
            if len(str(values.price_annual).split(".")[-1]) > 3:
                raise ValueError(f"price_annual must have at most 3 decimal places, got {values.price_annual}")

        return values


class EulaDocumentItem(BaseModel):
    """
    DocumentItem model
    """

    type: Literal["CustomEula", "StandardEula"]
    version: Optional[StrictStr] = Field(default=None)
    url: Optional[StrictStr] = Field(default=None)

    @model_validator(mode="after")
    def required_field_check_by_type(cls, values):
        if values.type == "CustomEula":
            if values.version is not None:
                raise ValueError("CustomEula can't pass version of standard document.")
            elif values.url is None:
                raise ValueError("CustomEula needs Url.")
        elif values.type == "StandardEula":
            if values.url is not None:
                raise ValueError("StandardEula cannot have a custom document Url.")
            elif values.version is None:
                raise ValueError("Specify version of StandardEula")
        return values


class AmiProductPricingTerm(Enum):
    HOURLY = "UsageBasedPricingTerm"
    UPFRONT_PRICING = "ConfigurableUpfrontPricingTerm"
    RECURRING_MONTHLY = "RecurringPaymentTerm"


class AmiProductPricingType(Enum):
    HOURLY = 1
    HOURLY_WITH_ANNUAL = 2
    HOURLY_WITH_MONTHLY_SUBSCRIPTION_FEE = 3


class Offer(BaseModel):
    """
    Offer model
    """

    eula_document: List[EulaDocumentItem] = Field(min_length=1)
    instance_types: List[InstanceTypePricing] = Field(min_length=1)
    monthly_subscription_fee: Annotated[Optional[Decimal], Field(default=None, ge=0.00)]
    refund_policy: str = Field(max_length=500)

    @field_validator("monthly_subscription_fee", mode="after")
    def check_decimal_precision(cls, value):
        if value is not None:
            if len(str(value).split(".")[-1]) > 3:
                raise ValueError(f"price must have at most 3 decimal places, got {value}")

        return value

    def get_offer_type(self) -> AmiProductPricingType:
        """Inspect offer and translate to the appropriate AmiProductOfferType"""
        t = None
        if self.monthly_subscription_fee is not None:
            t = AmiProductPricingType.HOURLY_WITH_MONTHLY_SUBSCRIPTION_FEE
        elif any(i for i in self.instance_types if i.price_annual is not None):
            t = AmiProductPricingType.HOURLY_WITH_ANNUAL
        else:
            t = AmiProductPricingType.HOURLY

        return t

    @classmethod
    def get_offer_type_from_offer_terms(cls, terms: list[Dict[str, Any]]) -> AmiProductPricingType:
        """Inspect offer details and translate to the appropriate AmiProductOfferType

        :param Dict[str, Any]: offer details from AWS API
        """

        configured_types = {i["Type"] for i in terms}

        def offer_has_types(target_types: list[AmiProductPricingTerm]):
            return all(t.value in configured_types for t in target_types)

        if offer_has_types([AmiProductPricingTerm.HOURLY, AmiProductPricingTerm.UPFRONT_PRICING]):
            return AmiProductPricingType.HOURLY_WITH_ANNUAL
        elif offer_has_types([AmiProductPricingTerm.HOURLY, AmiProductPricingTerm.RECURRING_MONTHLY]):
            return AmiProductPricingType.HOURLY_WITH_MONTHLY_SUBSCRIPTION_FEE
        else:
            return AmiProductPricingType.HOURLY

    @model_validator(mode="after")
    def check_pricing_type_alignment(cls, offer):
        """
        ensures instance types cannot have pricing set in a way that leaves
        ambiguity on if the configuration is intended to be one of:

        1. hourly
        2. hourly + annual
        3. hourly + monthly sub

        :param Offer offer: current offer to validate
        """
        if offer.monthly_subscription_fee is not None:
            cls._raise_on_missing_monthly_subscription_fields(offer)
        else:
            cls._raise_on_hourly_yearly_mismatch(offer)
        return offer

    @classmethod
    def _raise_on_missing_monthly_subscription_fields(cls, offer: Offer):
        misconfigured = "\n".join({i.name for i in offer.instance_types if i.price_annual is not None})
        if misconfigured:
            error_message = f"""Offer has monthly_subscription_fee but some instances have yearly key:
                {misconfigured}
                """
            raise ValueError(error_message)

    @classmethod
    def _raise_on_hourly_yearly_mismatch(cls, offer: Offer):
        yearly_count = 0
        hourly_count = 0
        hourly = set()
        yearly = set()
        all_types = set()
        for i in offer.instance_types:
            all_types.add(i.name)
            if i.price_annual is not None:
                yearly.add(i.name)
                yearly_count += 1
            if i.price_hourly is not None:
                hourly.add(i.name)
                hourly_count += 1

        if yearly_count != 0 and yearly_count < hourly_count:
            missing = "\n".join(all_types - yearly)
            raise ValueError(
                f"""Offer has at least one yearly price but some instances are missing yearly key:
                {missing}
                """
            )
        elif hourly_count < yearly_count:
            missing = "\n".join(all_types - hourly)
            raise ValueError(
                f"""Offer has at least one yearly price but some instances are missing yearly key:
                {missing}
                """
            )

    @model_validator(mode="after")
    def ensure_pricing_ordering_enforced(cls, offer):
        def hourly_greater_than_annual(i: InstanceTypePricing):
            return i.price_annual and (i.price_hourly > i.price_annual)

        misconfigured_hourly = "\n".join(i.name for i in offer.instance_types if hourly_greater_than_annual(i))
        error = ""
        if misconfigured_hourly:
            error += "Hourly pricing cannot be greater than yearly pricing. Misconfigured instance types: {misconfigured_hourly}"

        if error:
            raise ValueError(error)

        return offer


class Region(BaseModel):
    commercial_regions: conlist(str)  # type:ignore
    future_region_support: bool

    @field_validator("commercial_regions")
    def commercial_region_validator(cls, value):
        client = boto3.client("ec2")
        gov_regions = ["us-gov-east-1", "us-gov-west-1"]
        available_regions = [region["RegionName"] for region in client.describe_regions()["Regions"]] + gov_regions

        invalid_regions = set(value) - set(available_regions)
        if invalid_regions:
            raise ValueError(f"{invalid_regions} are not valid for commercial regions")
        return value

    def future_region_supported(self) -> List[str]:
        return ["All" if self.future_region_support else "None"]


class SupportResourcesItem(TypedDict):
    Text: str
    Url: str


SupportResources = List[SupportResourcesItem]
YamlSupportResourcesItem = Dict[str, str]
YamlSupportResources = List[YamlSupportResourcesItem]


def strip_string(field: str) -> str:
    return field.strip()


class Description(BaseModel):
    class Config:
        validate_assignment = True

    product_title: str = Field(max_length=72)
    short_description: str = Field(max_length=1000)
    long_description: str = Field(max_length=5000)
    logourl: HttpUrl
    highlights: conlist(str, min_length=1, max_length=3)  # type:ignore
    categories: conlist(str, min_length=1, max_length=3)  # type:ignore
    search_keywords: conlist(str, min_length=1)  # type:ignore
    support_description: str = Field(max_length=2000)
    support_resources: Optional[List[str]] = Field(default=[])
    sku: Optional[str] = Field(max_length=100, default=None)
    video_urls: Optional[conlist(HttpUrl, min_length=0, max_length=1)] = Field(default=[])  # type:ignore
    additional_resources: Optional[conlist(Dict[str, HttpUrl], min_length=0, max_length=3)] = Field(  # type:ignore
        default=[]
    )

    # validators
    format_support_description = field_validator("support_description")(strip_string)
    format_long_description = field_validator("long_description")(strip_string)

    @field_validator("highlights")
    def highlights_validator(cls, value):
        highlights = value
        invalid_values = []

        # Each field can be up to 500 characters
        for highlight in highlights:
            if len(highlight) > 500:
                invalid_values.append(highlight)
        if invalid_values:
            raise ValueError(
                f"Hightlights were too long, rephrase highlights "
                f"{'and'.join(invalid_values)}to be lss than 500 characters."
            )
        return value

    @field_validator("categories")
    def categories_validator(cls, value):
        categories = value
        # Each categories should be listed in
        # https://docs.aws.amazon.com/marketplace/latest/buyerguide/buyer-product-categories.html
        # Load config file
        invalid_values = set(categories) - set(CATEGORIES)
        if invalid_values:
            raise ValueError(f"{invalid_values} are not valid for categories")
        return value

    @field_validator("search_keywords")
    def keywords_validator(cls, value):
        keywords = value
        if len("".join(keywords)) > 250:
            raise ValueError("Combined character count of keywords can be at most 250 characters.")
        return value

    @field_validator("additional_resources")
    @classmethod
    def additional_resources_to_api_format(cls, additional_resources: YamlSupportResources) -> SupportResources:
        """Convert input description.additional_resources format to api format."""
        return [{"Text": key, "Url": str(url)} for item in additional_resources for key, url in item.items()]


class AmiVersion(BaseModel):
    version_title: str = Field(min_length=1)
    release_notes: str = Field(max_length=30000)
    ami_id: str = Field(max_length=21)
    access_role_arn: str = Field(max_length=150)
    os_user_name: str = Field(max_length=100)
    os_system_name: constr(to_upper=True)  # type:ignore
    os_system_version: str = Field(max_length=100)
    scanning_port: int = Field(gt=1, le=65535)
    usage_instructions: str = Field(max_length=2000)
    recommended_instance_type: str = Field(max_length=27)
    ip_protocol: Literal["tcp", "udp"]
    ip_ranges: conlist(str, min_length=0, max_length=5)  # type:ignore
    to_port: int = Field(gt=1, le=65535)
    from_port: int = Field(gt=1, le=65535)

    @field_validator("ami_id")
    def ami_id_validator(cls, value):
        if not value.startswith("ami-"):
            raise ValueError(f"{value} is not right ami-id. Id should start with `ami-`.")
        return value

    @field_validator("access_role_arn")
    def ami_access_role_arn_validator(cls, value):
        if not value.startswith("arn:aws:iam::"):
            raise ValueError(f"{value} is invalid role format. Please check your role again.")
        return value


class AmiProduct(BaseModel):
    """
    Ami Product model
    """

    description: Description
    region: Region
    version: AmiVersion


class DescriptionModel(BaseModel):
    """
    Model for description details from entity details
    """

    ProductTitle: str
    ShortDescription: str
    LongDescription: str
    Sku: Optional[str] = Field(default=None)
    Highlights: List[str]
    SearchKeywords: List[str]
    Categories: List[str]

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of description information with local configuration field names

        :return: Dictionary of description information
        :rtype: dict[str, Any]
        """
        return {
            "product_title": self.ProductTitle,
            "short_description": self.ShortDescription,
            "long_description": LiteralString(self.LongDescription),
            "sku": self.Sku,
            "highlights": self.Highlights,
            "search_keywords": self.SearchKeywords,
            "categories": self.Categories,
        }


class PromotionalResourcesModel(BaseModel):
    """
    Model for promotional resource details from entity details
    """

    LogoUrl: HttpUrl
    Videos: List[dict[str, Any]]
    AdditionalResources: YamlSupportResources

    @field_validator("AdditionalResources")
    def additional_resources_validator(cls, value) -> SupportResources:
        # The Ami class takes url as HttpUrl and converts it to string format for API request.
        # And HttpUrl adds a trailing slash to the end of a URL.
        # To compare values correctly, the link value from entity's AdditionalResources field also
        # needs to be converted to an HttpUrl and then back to string format.
        return [{"Text": resource["Text"], "Url": str(HttpUrl(resource["Url"]))} for resource in value]

    @field_validator("Videos")
    def videos_validator(cls, value) -> List:
        # The Ami class takes url as HttpUrl and converts it to string format for API request.
        # And HttpUrl adds a trailing slash to the end of a URL.
        # To compare values correctly, the link value from entity's Videos field also
        # needs to be converted to an HttpUrl and then back to string format.
        return [HttpUrl(value[0]["Url"])] if value else []

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of promotional resource information with local configuration field names

        :return: Dictionary of promotional resource information
        :rtype: dict[str, Any]
        """
        resources = []
        for resource in self.AdditionalResources:
            resources.append({resource["Text"]: resource["Url"]})

        return {
            "logourl": str(self.LogoUrl),
            "video_urls": [str(video) for video in self.Videos],
            "additional_resources": resources,
        }


class SupportInformationModel(BaseModel):
    """
    Model for support information details from entity details
    """

    Description: str
    Resources: List[str]

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of support information with local configuration field names.

        :return: Dictionary of support information
        :rtype: dict[str, Any]
        """
        return {"support_description": LiteralString(self.Description), "support_resources": self.Resources}


class RegionAvailabilityModel(BaseModel):
    """
    Model for region availability information details from entity details
    """

    Regions: List[str]
    FutureRegionSupport: str

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of region availability with local configuration field names.

        :return: Dictionary of region availability information
        :rtype: dict[str, Any]
        """
        future_region_support = True if self.FutureRegionSupport == "All" else False
        return {"commercial_regions": self.Regions, "future_region_support": future_region_support}


class SupportTermModel(BaseModel):
    """
    Model for support term details from entity details
    """

    Type: Literal["SupportTerm"] = "SupportTerm"
    RefundPolicy: str = Field(max_length=500)


class SelectorModel(BaseModel):
    """
    Duration detail model from annual pricing details
    """

    Type: Literal["Duration"]
    Value: str


class ConstraintsModel(BaseModel):
    """
    Constraint detail model from annual pricing details
    """

    MultipleDimensionSelection: Literal["Allowed", "Disallowed"]
    QuantityConfiguration: Literal["Allowed", "Disallowed"]


class RateCardModel(BaseModel):
    """
    Pricing ratecard model
    """

    DimensionKey: str
    Price: str


class RateCardItemsModel(BaseModel):
    """
    RateCard items in the details
    """

    Selector: Optional[SelectorModel] = Field(default=None)
    Constraints: Optional[ConstraintsModel] = Field(default=None)
    RateCard: List[RateCardModel]


class PricingTermModel(BaseModel):
    """
    Model for pricing term details from entity details
    """

    Type: Literal["UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"]
    CurrencyCode: Literal["USD"]
    RateCards: List[RateCardItemsModel]


class OperatingSystemModel(BaseModel):
    """
    Model for Operating system
    """

    Name: str
    Version: str
    Username: str
    ScanningPort: int

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of operating system with local configuration field names.

        :return: Dictionary of operating system information
        :rtype: dict[str, Any]
        """
        return {
            "os_system_name": self.Name,
            "os_user_name": self.Username,
            "os_system_version": self.Version,
            "scanning_port": self.ScanningPort,
        }


class SourcesModel(BaseModel):
    """
    Model for sources
    """

    Image: str
    OperatingSystem: OperatingSystemModel

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of source information with local configuration field names.

        :return: Dictionary of source information
        :rtype: dict[str, Any]
        """
        return {**{"ami_id": self.Image}, **self.OperatingSystem.to_dict()}


class SecurityGroupsModel(BaseModel):
    """
    Model for security groups
    """

    Protocol: Literal["tcp", "udp"]
    FromPort: int
    ToPort: int
    CidrIps: List[str]

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of security group information with local configuration field names.

        :return: Dictionary of security group information
        :rtype: dict[str, Any]
        """
        return {
            "ip_protocol": self.Protocol,
            "ip_ranges": self.CidrIps,
            "from_port": self.FromPort,
            "to_port": self.ToPort,
        }


class RecommendationsModel(BaseModel):
    """
    Model for recommendations
    """

    SecurityGroups: List[SecurityGroupsModel]
    InstanceType: str

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of version information with local configuration field names.

        Local config file only have the initial security group information of the version

        :return: Dictionary of recommendation information
        :rtype: dict[str, Any]
        """
        return {**{"recommended_instance_type": self.InstanceType}, **self.SecurityGroups[0].to_dict()}


class DeliveryMethodsModel(BaseModel):
    """
    Model for delivery method
    """

    Instructions: dict[str, str]
    Recommendations: RecommendationsModel

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of delivery method information with local configuration field names.

        :return: Dictionary of version information
        :rtype: dict[str, Any]
        """
        return {**{"usage_instructions": LiteralString(self.Instructions["Usage"])}, **self.Recommendations.to_dict()}


class VersionModel(BaseModel):
    """
    Model for version from entity details
    """

    VersionTitle: str
    ReleaseNotes: str
    Sources: List[SourcesModel]
    DeliveryMethods: List[DeliveryMethodsModel]

    def to_dict(self) -> dict[str, Any]:
        """
        Return dictionary of version information with local configuration field names.

        Only first sources and delivery method will be returned for the version.

        :return: Dictionary of version information
        :rtype: dict[str, Any]
        """
        sources = self.Sources[0].to_dict()
        delivery_methods = self.DeliveryMethods[0].to_dict()

        return {
            **{
                "version_title": self.VersionTitle,
                "release_notes": self.ReleaseNotes,
                "access_role_arn": "arn:aws:iam::stub_policy",
            },
            **self.DeliveryMethods[0].to_dict(),
            **self.Sources[0].to_dict(),
        }


class DiffAddedModel(BaseModel):
    """
    Model for fields that have been added in a diff comparison
    """

    name: str
    value: Any


class DiffRemovedModel(BaseModel):
    """
    Model for fields that have been removed in a diff comparison
    """

    name: str
    value: Any


class DiffChangedModel(BaseModel):
    """
    Model for fields that have been changed in a diff comparison
    """

    name: str
    old_value: Any
    new_value: Any


class DiffModel(BaseModel):
    """
    The result of a diff comparison, tracking changes to fields.
    """

    added: List[DiffAddedModel]
    removed: List[DiffRemovedModel]
    changed: List[DiffChangedModel]

    def __repr__(self):
        return self.model_dump_json(indent=2)


class EntityModel(BaseModel):
    """
    Entity model to get details information
    """

    Description: DescriptionModel
    PromotionalResources: PromotionalResourcesModel
    SupportInformation: SupportInformationModel
    RegionAvailability: RegionAvailabilityModel
    Versions: VersionModel
    Terms: List[Annotated[Union[SupportTermModel, PricingTermModel], Field(discriminator="Type")]]

    def to_dict(self) -> dict[str, Any]:
        """
        Convert a entity object to dict with local config file field names

        :return: Dictionary of local configuration information
        :rtype: dcit[str, Any]
        """
        description_configs = {
            **self.Description.to_dict(),
            **self.PromotionalResources.to_dict(),
            **self.SupportInformation.to_dict(),
        }
        config = {
            "product": {
                "description": description_configs,
                "region": self.RegionAvailability.to_dict(),
                "version": self.Versions.to_dict(),
            },
            "offer": self._convert_terms_to_dict(),
        }

        return config

    def _convert_terms_to_dict(self) -> dict[str, Any]:
        """
        Convert terms JSON format to dict with local configuration field names.
        """
        yaml_config: dict[str, Any] = {}
        hourly, yearly = {}, {}
        pricings: List[dict] = []

        for term in self.Terms:
            if term.Type == "SupportTerm":
                yaml_config["refund_policy"] = LiteralString(term.RefundPolicy)
            else:
                # Pricing term
                if term.Type == "UsageBasedPricingTerm":
                    for card in term.RateCards[0].RateCard:
                        hourly[card.DimensionKey] = card.Price
                if term.Type == "ConfigurableUpfrontPricingTerm":
                    for card in term.RateCards[0].RateCard:
                        yearly[card.DimensionKey] = card.Price

        for key in hourly:
            pricing = {"name": key, "hourly": hourly[key]}
            if key in yearly:
                pricing["yearly"] = yearly[key]
            pricings.append(pricing)
        yaml_config["instance_types"] = pricings

        yaml_config["eula_document"] = [{"type": "CustomEula", "url": "https://example.com"}]

        return yaml_config

    @staticmethod
    def get_entity(response: dict[str, Any]) -> EntityModel:
        """
        Convert a dictionary response into an EntityModel object

        :param dict[str, Any] response: JSON output from `_driver.get_full_ami_details`
        :return: An instance of `EntityModel` create from the response
        :rtype: EntityModel
        """
        return EntityModel(**response)

    @staticmethod
    def _get_rate_cards_from_yaml(
        instance_types: List[InstanceTypePricing],
    ) -> Tuple[List[dict[str, Any]], List[dict[str, Any]]]:
        rate_card_hourly = []
        rate_card_annual = []
        for instance_type in instance_types:
            rate_card_hourly.append({"DimensionKey": instance_type.name, "Price": str(instance_type.price_hourly)})
            if "price_annual" in instance_type.__fields__ and instance_type.price_annual is not None:
                rate_card_annual.append({"DimensionKey": instance_type.name, "Price": str(instance_type.price_annual)})

        annual_card_items, hourly_card_items = [], []
        if rate_card_annual:
            annual_card_items.append(
                {
                    "Selector": {"Type": "Duration", "Value": "P365D"},
                    "Constraints": {"MultipleDimensionSelection": "Allowed", "QuantityConfiguration": "Allowed"},
                    "RateCard": rate_card_annual,
                }
            )
        hourly_card_items.append({"RateCard": rate_card_hourly})

        return hourly_card_items, annual_card_items

    @staticmethod
    def get_entity_from_yaml(yaml_config: dict[str, Any]) -> EntityModel:
        """
        Convert a dictionary config into an EntityModel object

        :param dict[str, Any] yaml_config: dictionary data from loading local yaml config file
        :return: An instance of `EntityModel` create from the yaml_config
        :rtype: EntityModel
        """

        ami_product = AmiProduct(**yaml_config["product"])
        ami_offer = Offer(**yaml_config["offer"])

        rate_cards_hourly, rate_cards_annual = EntityModel._get_rate_cards_from_yaml(ami_offer.instance_types)

        yaml_to_api_response: dict[str, Any] = {
            "Description": {
                "ProductTitle": ami_product.description.product_title,
                "ShortDescription": ami_product.description.short_description,
                "LongDescription": ami_product.description.long_description,
                "Sku": ami_product.description.sku,
                "Highlights": ami_product.description.highlights,
                "SearchKeywords": ami_product.description.search_keywords,
                "Categories": ami_product.description.categories,
            },
            "PromotionalResources": {
                "LogoUrl": ami_product.description.logourl,
                "Videos": (
                    [{"Url": ami_product.description.video_urls[-1]}] if ami_product.description.video_urls else []
                ),
                "AdditionalResources": ami_product.description.additional_resources,
            },
            "SupportInformation": {
                "Description": ami_product.description.support_description,
                "Resources": ami_product.description.support_resources,
            },
            "RegionAvailability": {
                "Regions": ami_product.region.commercial_regions,
                "FutureRegionSupport": ami_product.region.future_region_supported()[-1],
            },
            "Versions": {
                "ReleaseNotes": ami_product.version.release_notes,
                "VersionTitle": ami_product.version.version_title,
                "Sources": [
                    {
                        "Image": ami_product.version.ami_id,
                        "OperatingSystem": {
                            "Name": ami_product.version.os_system_name,
                            "Version": ami_product.version.os_system_version,
                            "Username": ami_product.version.os_user_name,
                            "ScanningPort": ami_product.version.scanning_port,
                        },
                    }
                ],
                "DeliveryMethods": [
                    {
                        "Instructions": {"Usage": ami_product.version.usage_instructions},
                        "Recommendations": {
                            "SecurityGroups": [
                                {
                                    "Protocol": ami_product.version.ip_protocol,
                                    "FromPort": ami_product.version.from_port,
                                    "ToPort": ami_product.version.to_port,
                                    "CidrIps": ami_product.version.ip_ranges,
                                }
                            ],
                            "InstanceType": ami_product.version.recommended_instance_type,
                        },
                    }
                ],
            },
            "Terms": [
                {"Type": "SupportTerm", "RefundPolicy": ami_offer.refund_policy},
                {"Type": "UsageBasedPricingTerm", "CurrencyCode": "USD", "RateCards": rate_cards_hourly},
            ],
        }
        if rate_cards_annual:
            yaml_to_api_response["Terms"].append(
                {"Type": "ConfigurableUpfrontPricingTerm", "CurrencyCode": "USD", "RateCards": rate_cards_annual}
            )

        return EntityModel(**yaml_to_api_response)

    @staticmethod
    def is_changed(name: str, value1: Any, value2: Any) -> bool:
        """
        Check if values are changed

        :param str key: Name of field of two values
        :param Any value1: The value to compare
        :param Any value2: The value to compare
        :return: True or False
        :rtypr: bool
        """
        # These fields don't need to consider the ordering between values.
        # If the items in the list are same, there will be no listing changes.
        non_ordered_fields = ["Regions"]

        if name in non_ordered_fields:
            return set(value1) != set(value2)
        else:
            return value1 != value2

        return False

    @staticmethod
    def get_diff_model_type(
        field_name: str, value1: Any, value2: Any
    ) -> Optional[Union[DiffAddedModel, DiffRemovedModel, DiffChangedModel]]:
        """
        Determine the type of diff by comparing values in the field between the Marketplace listing and the local config

        :param str field_name: The name of the field being compared
        :param Any value1: The value of the field in the Marketplace listing
        :param Any value2: The value of the field in the local config file
        :return: Types of diff models or None
        :rtype: Optional[Union[DiffAddedModel, DiffRemovedModel, DiffChangedModel]]
        """
        # These fields don't need to consider the ordering between values.
        # If the items in the list are same, there will be no listing changes.
        non_ordered_fields = ["Regions"]

        if not value1 and value2:
            return DiffAddedModel(name=field_name, value=value2)
        elif value1 and not value2:
            return DiffRemovedModel(name=field_name, value=value1)
        else:
            if EntityModel.is_changed(name=field_name, value1=value1, value2=value2):
                return DiffChangedModel(name=field_name, old_value=value1, new_value=value2)
        return None

    @staticmethod
    def add_to_diff_list(
        res: Optional[Union[DiffAddedModel, DiffRemovedModel, DiffChangedModel]],
        diff_added: List[DiffAddedModel],
        diff_removed: List[DiffRemovedModel],
        diff_changed: List[DiffChangedModel],
    ) -> None:
        """
        Add a diff model to the correct diff list

        :param Union[DiffAddedModel, DiffRemovedModel, DiffChangedModel, None]: The diff model instance to be added
        :param List[DiffAddedModel]: List of DiffAddedModel
        :param List[DiffRemovedModel]: List of DiffRemovedModel
        :param List[DiffChangedModel]: List of DiffChangedModel
        :return: None
        :rtype: None
        """
        if res is None:
            return

        if isinstance(res, DiffAddedModel):
            diff_added.append(res)
        elif isinstance(res, DiffRemovedModel):
            diff_removed.append(res)
        elif isinstance(res, DiffChangedModel):
            diff_changed.append(res)

    @staticmethod
    def _add_diff(
        key: str,
        val1: Any,
        val2: Any,
        diff_added: List[DiffAddedModel],
        diff_removed: List[DiffRemovedModel],
        diff_changed: List[DiffChangedModel],
    ) -> None:
        """
        helper function to get the diff model type and add to the diff list
        """
        res = EntityModel.get_diff_model_type(key, val1, val2)
        EntityModel.add_to_diff_list(res, diff_added, diff_removed, diff_changed)

    @staticmethod
    def _compare_rate_cards(
        term_type: str,
        entity_rate_cards: dict[str, Any],
        local_rate_cards: dict[str, Any],
        diff_added: List[DiffAddedModel],
        diff_removed: List[DiffRemovedModel],
        diff_changed: List[DiffChangedModel],
    ) -> None:
        """
        Helper function to compare ratecard
        """
        for dimension_key in local_rate_cards:
            if dimension_key not in entity_rate_cards:
                # instance type added
                EntityModel._add_diff(
                    term_type, None, local_rate_cards[dimension_key], diff_added, diff_removed, diff_changed
                )
            elif entity_rate_cards[dimension_key] != local_rate_cards[dimension_key]:
                # pricing changed
                EntityModel._add_diff(
                    term_type,
                    entity_rate_cards[dimension_key],
                    local_rate_cards[dimension_key],
                    diff_added,
                    diff_removed,
                    diff_changed,
                )

        for dimension_key in entity_rate_cards:
            # instance type removed
            if dimension_key not in local_rate_cards:
                EntityModel._add_diff(
                    term_type, entity_rate_cards[dimension_key], None, diff_added, diff_removed, diff_changed
                )

    def _get_diff_model(self, local_entity: EntityModel) -> DiffModel:
        """
        Get complete DiffModel instance of diff from listing and local config

        :param EntityModel local_entity: Entity object created by local configuration
        :return DiffModel with added, deleted and changed diff details
        :rtype DiffModel
        """
        non_dict_fields = ["Terms"]  # Terms contain different offer details with list format
        skip_fields = ["Versions"]
        diff_added: List[DiffAddedModel] = []
        diff_removed: List[DiffRemovedModel] = []
        diff_changed: List[DiffChangedModel] = []

        def _add_diff(key, val1, val2):
            res = EntityModel.get_diff_model_type(key, val1, val2)
            EntityModel.add_to_diff_list(res, diff_added, diff_removed, diff_changed)

        entity_model = self.model_dump()

        for entity_key, entity_value in local_entity.model_dump().items():
            if entity_key in skip_fields:
                continue
            if entity_key not in non_dict_fields:
                for model_key, model_value in entity_value.items():
                    EntityModel._add_diff(
                        model_key,
                        entity_model[entity_key][model_key],
                        model_value,
                        diff_added,
                        diff_removed,
                        diff_changed,
                    )
            else:
                for index, term in enumerate(entity_value):
                    if "Pricing" not in term["Type"]:
                        EntityModel._add_diff(
                            term["Type"], entity_model[entity_key][index], term, diff_added, diff_removed, diff_changed
                        )
                    else:
                        for item, value in term.items():
                            if item not in ["RateCards"]:
                                # currency code
                                EntityModel._add_diff(
                                    term["Type"],
                                    entity_model[entity_key][index][item],
                                    term[item],
                                    diff_added,
                                    diff_removed,
                                    diff_changed,
                                )
                            else:
                                for extra_item, value in term[item][-1].items():
                                    if extra_item not in ["RateCard"]:
                                        # selector, constraints
                                        EntityModel._add_diff(
                                            term["Type"],
                                            entity_model[entity_key][index][item][-1][extra_item],
                                            value,
                                            diff_added,
                                            diff_removed,
                                            diff_changed,
                                        )
                                    else:
                                        # Compare ratecards
                                        local_rate_cards = {
                                            card["DimensionKey"]: card for card in term[item][-1]["RateCard"]
                                        }
                                        entity_rate_cards = {
                                            card["DimensionKey"]: card
                                            for card in self.model_dump()[entity_key][index][item][-1]["RateCard"]
                                        }
                                        EntityModel._compare_rate_cards(
                                            term["Type"],
                                            entity_rate_cards,
                                            local_rate_cards,
                                            diff_added,
                                            diff_removed,
                                            diff_changed,
                                        )

        return DiffModel(added=diff_added, removed=diff_removed, changed=diff_changed)

    def get_diff(self, local_entity: EntityModel) -> DiffModel:
        return self._get_diff_model(local_entity)
