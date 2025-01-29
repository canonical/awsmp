from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, TypedDict

import boto3
from pydantic import BaseModel, Field, HttpUrl, conlist, constr, field_validator

from awsmp.constants import CATEGORIES


class InstanceTypePricing(BaseModel):
    name: str
    price_hourly: Decimal = Field(ge=0.0, decimal_places=4)
    price_annual: Decimal = Field(ge=0.0, decimal_places=4)


class Region(BaseModel):
    commercial_regions: conlist(str)  # type:ignore
    future_region_support: bool

    @field_validator("commercial_regions")
    def commercial_region_validator(cls, value):
        client = boto3.client("ec2")
        available_regions = [region["RegionName"] for region in client.describe_regions()["Regions"]]
        if value[0] == "all":
            return available_regions
        else:
            invalid_regions = set(value) - set(available_regions)
            if invalid_regions:
                raise ValueError(f"{invalid_regions} are not valid for commercial regions")
            return value

    @field_validator("future_region_support")
    def future_region_support_validator(cls, value):
        return ["All" if value else "None"]


class SupportResourcesItem(TypedDict):
    Text: str
    Url: str


SupportResources = List[SupportResourcesItem]
YamlSupportResourcesItem = Dict[str, str]
YamlSupportResources = List[YamlSupportResourcesItem]


def strip_string(field: str) -> str:
    return field.strip()


class AmiProduct(BaseModel):
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
    support_resources: Optional[str] = Field(max_length=500, default=None)
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
    version_title: str = Field(max_length=36)
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


class DescriptionModel(BaseModel):
    ProductTitle: str
    ProductCode: str
    ShortDescription: str
    LongDescription: str
    Sku: str
    Highlights: List[str]
    SearchKeywords: List[str]
    Categories: List[str]

class PromotionalResourcesModel(BaseModel):
    LogoUrl: str
    Videos: List[str]
    AdditionalResources: List[dict[str, str]]

class SupportInformationModel(BaseModel):
    Description: str
    Resources: List[str]

class RegionAvailabilityModel(BaseModel):
    Regions: List[str]
    FutureRegionSupport: str

class Entity(BaseModel):
    Description: DescriptionModel
    PromotionalResources: PromotionalResourcesModel
    SupportInformation: SupportInformationModel
    RegionAvailability: RegionAvailabilityModel

    @staticmethod
    def _get_entity(response: dict[str, Any]):
        return Entity(**response)

    def _get_description_diff(self, local_config: AmiProduct):

        desc = self.Description
        promo = self.PromotionalResources
        support = self.SupportInformation

        json_yaml_description_mapping = {
            "product_title": desc.ProductTitle,
            "short_description": desc.ShortDescription,
            "long_description": desc.LongDescription,
            "highlights": desc.Highlights,
            "logourl": promo.LogoUrl,
            "search_keywords": desc.SearchKeywords,
            "support_description": support.Description,
            "categories": desc.Categories,
        }

        live_listing_config = AmiProduct(**json_yaml_description_mapping)
        diffs = {}

        for k, v in live_listing_config.dict().items():
            local_value = local_config.dict()[k]
            if local_value != v:
                diffs[k] = local_value

        return diffs

    def _get_region_diff(self, local_config: Region):
        regions = self.RegionAvailability

        json_yaml_region_mapping = {
            "commercial_regions": regions.Regions,
            "future_region_support": True if regions.FutureRegionSupport == "All" else False,
        }

        live_listing_config = Region(**json_yaml_region_mapping)

        diffs = {}

        for k, v in live_listing_config.dict().items():
            amiRegion_value = local_config.dict()[k]
            if amiRegion_value != v:
                if k == "commercial_regions":
                    diffs[k] = list(set(amiRegion_value) - set(v))
                else:
                    diffs[k] = amiRegion_value

        return diffs

    def _get_support_and_legal_diff(self, support_term: dict[str, Any], legal_term: str):
        # FIX ME legal term is not described from desribe_entity call
        # getting diff of the support term for now
        support = self.SupportInformation

        response_support_mapping = {"description": support.Description, "resources": support.Resources}
        diffs = {}

        # support_term
        for k, v in response_support_mapping.items():
            if support_term[k] != v:
                diffs[k] = support_term[k]

        return diffs
    
    def get_diff(self, ami: AmiProduct, ami_region: Region, support_term: dict[str, Any], legal_term: str):

        desc_diff = self._get_description_diff(ami)
        region_diff = self._get_region_diff(ami_region)
        support_diff = self._get_support_and_legal_diff(support_term, legal_term)

        total_diff = [desc_diff, region_diff, support_diff]

        return total_diff
