import json
from typing import Any, Optional, cast
from unittest.mock import patch

import pytest
import yaml
from pydantic import HttpUrl, ValidationError

from awsmp import _driver, models


@pytest.fixture
def mock_boto3():
    with patch("awsmp.models.boto3") as mock_boto3:
        mock_boto3.client.return_value.describe_regions.return_value = {
            "Regions": [
                {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
                {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
            ]
        }
        yield mock_boto3


class TestAmiDescriptionSuite:
    def _build_ami_description(self, **kwargs):
        defaults = dict(
            product_title="p" * 72,
            short_description="short_description",
            long_description="long_descrption",
            logourl="https://some-url",
            highlights=["highlight1"],
            categories=["Storage"],
            search_keywords=["one_term"],
            support_description="supported!",
        )
        return models.Description(**(defaults | kwargs))

    @pytest.mark.parametrize(
        "provided_keys,expected",
        [
            ([], []),
            ([{"some_key": "http://some_value"}], [{"Text": "some_key", "Url": "http://some_value/"}]),
            (
                [{f"k{i}": f"http://url{i}/"} for i in range(3)],
                [{"Text": f"k{i}", "Url": f"http://url{i}/"} for i in range(3)],
            ),
        ],
    )
    def test_should_convert_additional_resources_to_api_format(self, provided_keys, expected):
        product = self._build_ami_description(additional_resources=provided_keys)
        assert product.additional_resources == expected

    @pytest.mark.parametrize("ami_product_field", ["support_description", "long_description"])
    def test_should_strip_new_lines_from_relevent_fields(self, ami_product_field):
        valid_description = "my description\n\nafter separator"
        product = self._build_ami_description(**{ami_product_field: f"\n\n\n{valid_description}\n\n"})
        assert getattr(product, ami_product_field) == valid_description

    def test_search_keywords_should_not_accept_large_input(self):
        keywords = ["a" * 150, "b" * 105, "c", "d", "e"]
        with pytest.raises(ValueError) as e:
            self._build_ami_description(search_keywords=keywords)
        err = "Combined character count of keywords can be at most 250 characters"
        assert err in str(e.value)


class TestRegion:
    def test_region_availability(self, mock_boto3):
        region = models.Region(commercial_regions=["us-east-1", "us-east-2"], future_region_support=True)
        assert region.future_region_support == True

    def test_region_availability_invalid_regions(self, mock_boto3):
        with pytest.raises(ValidationError):
            models.Region(commercial_regions=["us-east-1", "us-west-1"], future_region_support=True)

    def test_region_availability_future_region_supported(self, mock_boto3):
        region = models.Region(commercial_regions=["us-east-1", "us-east-2"], future_region_support=False)
        assert region.future_region_supported() == ["None"]


class TestAmiVersion:
    def _get_version_details(self):
        return {
            "version_title": "test_version_title",
            "release_notes": "test_release_notes\n",
            "ami_id": "ami-test",
            "access_role_arn": "arn:aws:iam::test",
            "os_user_name": "test_os_user_name",
            "os_system_version": "test_os_system_version",
            "os_system_name": "test_os",
            "scanning_port": 22,
            "usage_instructions": "test_usage_instructions",
            "recommended_instance_type": "m5.large",
            "ip_protocol": "tcp",
            "ip_ranges": ["0.0.0.0/0"],
            "from_port": 22,
            "to_port": 22,
        }

    def test_version_ami_id(self):
        model = models.AmiVersion(**self._get_version_details())
        assert model.ami_id == "ami-test"

    def test_version_ip_ranges(self):
        model = models.AmiVersion(**self._get_version_details())
        assert model.ip_ranges == ["0.0.0.0/0"]

    def test_invalid_access_role_arn(self):
        version = self._get_version_details()
        version["access_role_arn"] = "arn:iam::test"
        with pytest.raises(ValidationError):
            models.AmiVersion(**version)

    def test_invalid_ami_id(self):
        version = self._get_version_details()
        version["ami_id"] = "1234567"
        with pytest.raises(ValidationError):
            models.AmiVersion(**version)


class TestAmiProduct:
    @pytest.fixture
    def local_config(self):
        with open("./tests/test_config.yaml", "r") as f:
            return yaml.safe_load(f)

    def test_ami_product_short_description(self, mock_boto3, local_config):
        ami_product = models.AmiProduct(**local_config["product"])
        assert (
            ami_product.description.short_description == "test_short_description"
            and ami_product.description.product_title == "test"
        )

    def test_ami_product_region_availability(self, mock_boto3, local_config):
        ami_product = models.AmiProduct(**local_config["product"])
        assert ami_product.region.commercial_regions == ["us-east-1", "us-east-2"]

    def test_ami_product_version(self, mock_boto3, local_config):
        ami_product = models.AmiProduct(**local_config["product"])
        assert ami_product.version.ami_id == "ami-test"

    def test_ami_product_invalid_description(self, mock_boto3, local_config):
        local_config["product"]["description"]["categories"] = ["test"]
        with pytest.raises(ValidationError):
            ami_product = models.AmiProduct(**local_config["product"])

    def test_ami_product_invalid_region(self, mock_boto3, local_config):
        local_config["product"]["region"]["commercial_regions"].append("eu-west-3")
        with pytest.raises(ValidationError):
            ami_product = models.AmiProduct(**local_config["product"])


class TestInstanceTypePricing:
    @pytest.mark.parametrize(
        "instance_type_and_pricing,expected_hourly,expected_yearly",
        [
            ({"name": "c1.medium", "hourly": 0.004, "yearly": 24.528}, "0.004", "24.528"),
            ({"name": "c3.medium", "hourly": 0.012}, "0.012", "None"),
            ({"name": "c1.metal", "hourly": 0, "yearly": 0}, "0", "0"),
        ],
    )
    def test_instance_type_pricing(self, instance_type_and_pricing, expected_hourly, expected_yearly):
        model = models.InstanceTypePricing(**instance_type_and_pricing)
        assert str(model.price_hourly) == expected_hourly and str(model.price_annual) == expected_yearly

    def test_instance_type_without_hourly_pricing(self):
        instance_type_and_pricing: dict[str, Any] = {
            "name": "c1.medium",
        }

        with pytest.raises(ValidationError):
            models.InstanceTypePricing(**instance_type_and_pricing)

    def test_instance_type_with_four_digits(self):
        instance_type_and_pricing: dict[str, Any] = {
            "name": "c1.medium",
            "hourly": 0.0045,
            "yearly": 24.528,
        }

        with pytest.raises(ValidationError) as e:
            models.InstanceTypePricing(**instance_type_and_pricing)

        assert "must have at most 3 decimal places" in str(e.value)


class TestEulaDocumentItem:
    @pytest.mark.parametrize(
        "eula_item,expected_url,expected_version",
        [
            ({"type": "CustomEula", "url": "https://eula.com"}, "https://eula.com", None),
            ({"type": "StandardEula", "version": "2022-07-14"}, None, "2022-07-14"),
        ],
    )
    def test_eula_document_item(self, eula_item, expected_url, expected_version):
        model = models.EulaDocumentItem(**eula_item)
        assert model.url == expected_url and model.version == expected_version

    @pytest.mark.parametrize(
        "eula_item,expected_error_msg",
        [
            (
                {"type": "CustomEula", "url": "https://eula.com", "version": "2024-05-07"},
                "CustomEula can't pass version",
            ),
            ({"type": "StandardEula", "url": "https://eula.com"}, "StandardEula cannot have a custom document Url."),
            ({"type": "CustomEula"}, "CustomEula needs Url."),
            ({"type": "StandardEula"}, "Specify version of StandardEula"),
        ],
    )
    def test_eula_document_item_required_field_check_by_type(self, eula_item, expected_error_msg):
        with pytest.raises(ValidationError) as e:
            models.EulaDocumentItem(**eula_item)
        assert expected_error_msg in str(e.value)


class TestOffer:
    def _get_offer_details(self):
        return {
            "eula_document": [{"type": "CustomEula", "url": "https://eula.com"}],
            "instance_types": [
                {"name": "c3.medium", "hourly": 0.012, "yearly": 57.528},
                {"name": "c4.large", "hourly": 0.078, "yearly": 123.456},
            ],
            "refund_policy": "This is refund policy",
        }

    def test_refund_policy_from_offer(self):
        model = models.Offer(**self._get_offer_details())
        assert model.refund_policy == "This is refund policy"

    def test_invalid_refund_policy_from_offer_too_long(self):
        offer_detail = self._get_offer_details()
        offer_detail["refund_policy"] = "refund policy" * 50
        with pytest.raises(ValidationError):
            models.Offer(**offer_detail)

    def test_eula_document_from_offer(self):
        model = models.Offer(**self._get_offer_details())
        assert model.eula_document[0].url == "https://eula.com"

    def test_invalid_eula_document_from_offer_with_version(self):
        offer_detail = self._get_offer_details()
        offer_detail["eula_document"][0]["version"] = "2025-02-04"
        with pytest.raises(ValidationError):
            models.Offer(**offer_detail)

    def test_instance_type_and_pricing_from_offer(self):
        model = models.Offer(**self._get_offer_details())
        assert model.instance_types[1].name == "c4.large" and str(model.instance_types[1].price_annual) == "123.456"

    def test_invalid_instance_type_and_pricing_without_pricing(self):
        offer_detail = self._get_offer_details()
        offer_detail["instance_types"][1] = {"name": "c4.large"}
        with pytest.raises(ValidationError):
            models.Offer(**offer_detail)

    def test_monthly_subscription_fee(self):
        offer_detail = self._get_offer_details()
        for i in offer_detail["instance_types"]:
            del i["yearly"]

        offer_detail["monthly_subscription_fee"] = 50.04

        model = models.Offer(**offer_detail)
        assert str(model.monthly_subscription_fee) == "50.04"

    def test_invalid_monthly_subscription_fee(self):
        offer_detail = self._get_offer_details()
        offer_detail["monthly_subscription_fee"] = 50.01234
        with pytest.raises(ValidationError) as e:
            models.Offer(**offer_detail)

        assert "must have at most 3 decimal places" in str(e.value)

    @pytest.mark.parametrize(
        "instance_types,monthly_fee,expected_type",
        [
            ([{"name": "c1.large", "hourly": 0.0, "yearly": None}], None, models.AmiProductPricingType.HOURLY),
            (
                [{"name": "c2.large", "hourly": 0.0, "yearly": 0.0}],
                None,
                models.AmiProductPricingType.HOURLY_WITH_ANNUAL,
            ),
            (
                [{"name": "c3.xlarge", "hourly": 0.0, "yearly": None}],
                0.0,
                models.AmiProductPricingType.HOURLY_WITH_MONTHLY_SUBSCRIPTION_FEE,
            ),
        ],
    )
    def test_should_be_able_to_get_offer_type_from_offer(
        self, instance_types: list[dict], monthly_fee: float, expected_type: models.AmiProductPricingType
    ):
        offer_item = {
            "eula_document": [{"type": "CustomEula", "url": "https://example.com"}],
            "refund_policy": "no refund",
            "instance_types": instance_types,
            "monthly_subscription_fee": monthly_fee,
        }
        o = models.Offer(**offer_item)  # type: ignore
        assert o.get_offer_type() == expected_type

    @pytest.mark.parametrize(
        "instance_types,monthly_fee",
        [
            (
                [
                    {"name": "c1.large", "hourly": 0.0, "yearly": 0.0},
                    {"name": "c1.xlarge", "hourly": 0.0},
                ],
                None,
            ),
            ([{"name": "c3.large", "hourly": 0.0}, {"name": "c3.xlarge", "hourly": 0.0, "yearly": 0.0}], 0.0),
        ],
    )
    def test_should_prevent_mixed_pricing_types(self, instance_types: list[dict], monthly_fee: Optional[str]):
        """
        ensures instance types cannot have pricing
        set in a way that leaves ambiguity on if the
        configuration is intended to be one of:
        1. hourly
        2. hourly + annual
        3. hourly + monthly sub
        """
        offer_item = {
            "eula_document": [{"type": "CustomEula", "url": "https://example.com"}],
            "refund_policy": "no refund",
            "instance_types": instance_types,
            "monthly_subscription_fee": monthly_fee,
        }

        with pytest.raises(ValidationError) as e:
            models.Offer(**offer_item)  # type: ignore

    @pytest.mark.parametrize(
        "offer_details, expected_type",
        [
            (
                [{"Type": "UsageBasedPricingTerm"}],
                models.AmiProductPricingType.HOURLY,
            ),
            (
                [{"Type": "UsageBasedPricingTerm"}, {"Type": "ConfigurableUpfrontPricingTerm"}],
                models.AmiProductPricingType.HOURLY_WITH_ANNUAL,
            ),
            (
                [{"Type": "UsageBasedPricingTerm"}, {"Type": "RecurringPaymentTerm"}],
                models.AmiProductPricingType.HOURLY_WITH_MONTHLY_SUBSCRIPTION_FEE,
            ),
        ],
    )
    def test_should_be_able_to_get_offer_type_from_offer_terms(self, offer_details, expected_type):
        o = models.Offer.get_offer_type_from_offer_terms(offer_details)
        assert o == expected_type

    @pytest.mark.parametrize(
        "instance_types",
        [
            ([{"name": "c1.large", "hourly": 5.0, "yearly": 0.5}]),
            [{"name": "c3.xlarge", "hourly": 5.0, "yearly": 0.5}],
            [{"name": "c3.xlarge", "hourly": 5.0, "yearly": 0.5}, {"name": "c3.xlarge", "hourly": 5.0, "yearly": 0.3}],
            [{"name": "c3.xlarge", "hourly": 5.0, "yearly": 0.5}, {"name": "c3.xlarge", "hourly": 0.5, "yearly": 0.6}],
        ],
    )
    def test_should_enforce_hourly_cannot_be_greater_than_yearly(self, instance_types: list[dict]):
        """
        This validates that:
         1. hourly cannot be greater than annual
         2. yearly cannot be less than hourly
        """
        offer_item = {
            "eula_document": [{"type": "CustomEula", "url": "https://example.com"}],
            "refund_policy": "no refund",
            "instance_types": instance_types,
        }

        with pytest.raises(ValidationError) as e:
            models.Offer(**offer_item)  # type: ignore

        assert e.match("Hourly pricing cannot be greater than yearly pricing.")


class TestDescriptionModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("product_title", "test title"),
            ("short_description", "test short description"),
            ("long_description", "test long description\n"),
            ("sku", "test sku"),
            ("highlights", ["test highlight1"]),
            ("search_keywords", ["ubuntu"]),
            ("categories", ["test categories"]),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.DescriptionModel(
            ProductTitle="test title",
            ShortDescription="test short description",
            LongDescription="test long description\n",
            Sku="test sku",
            Highlights=["test highlight1"],
            SearchKeywords=["ubuntu"],
            Categories=["test categories"],
        ).to_dict()
        assert yaml_config[key] == value


class TestPricingTermModel:
    def test_pricing_term_model_hourly(self):
        data = {
            "Type": "UsageBasedPricingTerm",
            "CurrencyCode": "USD",
            "RateCards": [
                {
                    "RateCard": [
                        {"DimensionKey": "c1.medium", "Price": "0.004"},
                        {"DimensionKey": "c1.xlarge", "Price": "0.014"},
                        {"DimensionKey": "c3.2xlarge", "Price": "0.014"},
                        {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                    ]
                }
            ],
        }
        term = models.PricingTermModel(**data)  #  type: ignore
        assert term.RateCards[0].RateCard[1].DimensionKey == "c1.xlarge"

    def test_pricing_term_model_annual(self):
        data = {
            "Type": "ConfigurableUpfrontPricingTerm",
            "CurrencyCode": "USD",
            "RateCards": [
                {
                    "Selector": {"Type": "Duration", "Value": "P365D"},
                    "Constraints": {"MultipleDimensionSelection": "Allowed", "QuantityConfiguration": "Allowed"},
                    "RateCard": [
                        {"DimensionKey": "c1.medium", "Price": "24.0"},
                        {"DimensionKey": "c1.xlarge", "Price": "98.0"},
                        {"DimensionKey": "c3.2xlarge", "Price": "98.0"},
                        {"DimensionKey": "c3.4xlarge", "Price": "196.0"},
                    ],
                }
            ],
        }
        term = models.PricingTermModel(**data)  #  type: ignore
        selector = cast(models.SelectorModel, term.RateCards[0].Selector)
        assert term.RateCards[0].RateCard[1].DimensionKey == "c1.xlarge" and selector.Value == "P365D"

    def test_invalid_pricing_term_model(self):
        data = {
            "Type": "ConfigurableUpfrontPricingTerm",
            "CurrencyCode": "USD",
            "RateCards": [
                {
                    "Selector": {"Type": "Duration", "Value": "P365D"},
                    "Constraints": {"MultipleDimensionSelection": "Allowed"},
                    "RateCard": [
                        {"DimensionKey": "c1.medium", "Price": "24.0"},
                        {"DimensionKey": "c1.xlarge", "Price": "98.0"},
                        {"DimensionKey": "c3.2xlarge", "Price": "98.0"},
                        {"DimensionKey": "c3.4xlarge", "Price": "196.0"},
                    ],
                }
            ],
        }
        with pytest.raises(ValidationError) as e:
            models.PricingTermModel(**data)  #  type: ignore


class TestEntity:
    @pytest.fixture
    def get_entity(self):
        with open("./tests/test_config.json", "r") as f:
            response_json = json.load(f)

        with open("./tests/test_config.yaml", "r") as f:
            local_config = yaml.safe_load(f)

        # live_listing_response
        entity1 = models.EntityModel(**response_json)
        # local_config_response
        entity2 = models.EntityModel.get_entity_from_yaml(local_config)

        return entity1, entity2

    def test_valid_response(self):
        with open("./tests/test_config.json", "r") as f:
            response_json = json.load(f)

        entity_model = models.EntityModel(**response_json)
        assert entity_model.Description.ProductTitle == "test"

    def test_valid_response_version(self):
        with open("./tests/test_config.json", "r") as f:
            response_json = json.load(f)

        entity_model = models.EntityModel(**response_json)
        assert entity_model.Versions.ReleaseNotes == "test release notes"

    def test_valid_response_pricing_term(self):
        with open("./tests/test_config.json", "r") as f:
            response_json = json.load(f)

        entity_model = models.EntityModel(**response_json)
        pricing = cast(models.PricingTermModel, entity_model.Terms[1])
        assert pricing.RateCards[0].RateCard[0].DimensionKey == "a1.large"

    def test_yaml_to_entity(self, mock_boto3):
        with open("./tests/test_config.yaml", "r") as f:
            local_config = yaml.safe_load(f)

        entity_model = models.EntityModel.get_entity_from_yaml(local_config)
        assert entity_model.Description.ProductTitle == "test"

    def test_yaml_to_entity_version(self, mock_boto3):
        with open("./tests/test_config.yaml", "r") as f:
            local_config = yaml.safe_load(f)

        entity_model = models.EntityModel.get_entity_from_yaml(local_config)
        assert entity_model.Versions.ReleaseNotes == "test_release_notes\n"

    def test_yaml_to_entity_term(self, mock_boto3):
        with open("./tests/test_config.yaml", "r") as f:
            local_config = yaml.safe_load(f)

        entity_model = models.EntityModel.get_entity_from_yaml(local_config)
        refund_term = cast(models.SupportTermModel, entity_model.Terms[0])
        assert refund_term.RefundPolicy == "test_refund_policy_term\n"

    def test_non_valid_response(self):
        non_valid_response: dict[str, Any] = {
            "Description": {
                "ProductTitle": "test",
                "ProductCode": "prod-test",
            },
            "PromotionalResources": {
                "LogoUrl": "https://test-logourl",
            },
            "RegionAvailability": {"FutureRegionSupport": "All", "Restrict": [], "Regions": ["us-east-1", "us-east-2"]},
            "SupportInformation": {"Description": "test_support_description", "Resources": ["test_support_resource"]},
            "Versions": {"version1": ""},
        }
        with pytest.raises(ValidationError):
            models.EntityModel(**non_valid_response)

    @pytest.mark.parametrize(
        "name, value1, value2, expected",
        [
            ("test1", "", "test", models.DiffAddedModel(name="test1", value="test")),
            ("test2", "test", "", models.DiffRemovedModel(name="test2", value="test")),
            (
                "test3",
                "test",
                "testtest",
                models.DiffChangedModel(name="test3", old_value="test", new_value="testtest"),
            ),
        ],
    )
    def test_get_diff_model_type(self, name, value1, value2, expected):
        res = models.EntityModel.get_diff_model_type(name, value1, value2)
        assert res == expected

    @pytest.mark.parametrize(
        "custom_config, expected_diff",
        [
            (
                {},
                models.DiffModel(added=[], removed=[], changed=[]),
            ),
        ],
    )
    def test_get_changed_no_diff(self, mock_boto3, get_entity, custom_config, expected_diff):
        entity1, entity2 = get_entity

        for key, value in custom_config.items():
            setattr(entity2, key, value)
        assert entity1.get_diff(entity2) == expected_diff

    @pytest.mark.parametrize(
        "custom_config, expected_diff",
        [
            (
                {
                    "Description": models.DescriptionModel(
                        ProductTitle="test",
                        ShortDescription="test_short_description",
                        LongDescription="test",
                        Sku="test",
                        Highlights=["test_highlight_1"],
                        SearchKeywords=["test_keyword_1"],
                        Categories=["Migration"],
                    ),
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="LongDescription", old_value="test_long_description", new_value="test"
                        )
                    ],
                ),
            ),
            (
                {
                    "Description": models.DescriptionModel(
                        ProductTitle="test",
                        ShortDescription="test_short_description",
                        LongDescription="test",
                        Sku="test",
                        Highlights=["test_highlight_1", "test_highlight_2"],
                        SearchKeywords=["test_keyword_1"],
                        Categories=["Migration"],
                    ),
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="LongDescription", old_value="test_long_description", new_value="test"
                        ),
                        models.DiffChangedModel(
                            name="Highlights",
                            old_value=["test_highlight_1"],
                            new_value=["test_highlight_1", "test_highlight_2"],
                        ),
                    ],
                ),
            ),
        ],
    )
    def test_get_description_diff(self, mock_boto3, get_entity, custom_config, expected_diff):
        entity1, entity2 = get_entity
        for key, value in custom_config.items():
            setattr(entity2, key, value)
        assert entity1.get_diff(entity2) == expected_diff

    @pytest.mark.parametrize(
        "custom_config, expected_diff",
        [
            (
                {
                    "RegionAvailability": models.RegionAvailabilityModel(
                        Regions=["us-east-1"],
                        FutureRegionSupport="All",
                    ),
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="Regions", old_value=["us-east-1", "us-east-2"], new_value=["us-east-1"]
                        )
                    ],
                ),
            ),
        ],
    )
    def test_get_region_diff(self, mock_boto3, get_entity, custom_config, expected_diff):
        entity1, entity2 = get_entity
        for key, value in custom_config.items():
            setattr(entity2, key, value)
        assert entity1.get_diff(entity2) == expected_diff

    @pytest.mark.parametrize(
        "custom_config, expected_diff",
        [
            (
                {
                    "PromotionalResources": models.PromotionalResourcesModel(
                        LogoUrl="https://test-logourl",
                        Videos=[],
                        AdditionalResources=[{"Text": "test-link1", "Url": "https://test-url/"}],
                    ),
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="AdditionalResources",
                            old_value=[{"Text": "test-link", "Url": "https://test-url/"}],
                            new_value=[{"Text": "test-link1", "Url": "https://test-url/"}],
                        )
                    ],
                ),
            ),
            (
                {
                    "PromotionalResources": models.PromotionalResourcesModel(
                        LogoUrl="https://test-logourl",
                        Videos=[{"Type": "Link", "Title": "Product Video", "Url": "https://video-url"}],
                        AdditionalResources=[{"Text": "test-link", "Url": "https://test-url/"}],
                    ),
                },
                models.DiffModel(
                    added=[models.DiffAddedModel(name="Videos", value=[HttpUrl("https://video-url")])],
                    removed=[],
                    changed=[],
                ),
            ),
        ],
    )
    def test_get_promotional_resource_diff(self, mock_boto3, get_entity, custom_config, expected_diff):
        entity1, entity2 = get_entity
        for key, value in custom_config.items():
            setattr(entity2, key, value)
        assert entity1.get_diff(entity2) == expected_diff

    @pytest.mark.parametrize(
        "custom_config, expected_diff",
        [
            (
                [{"Type": "SupportTerm", "RefundPolicy": "will be refunded"}],
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="SupportTerm",
                            old_value={"Type": "SupportTerm", "RefundPolicy": "test_refund_policy_term\n"},
                            new_value={"Type": "SupportTerm", "RefundPolicy": "will be refunded"},
                        )
                    ],
                ),
            ),
            (
                [{"Type": "SupportTerm", "RefundPolicy": ""}],
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="SupportTerm",
                            old_value={"Type": "SupportTerm", "RefundPolicy": "test_refund_policy_term\n"},
                            new_value={"Type": "SupportTerm", "RefundPolicy": ""},
                        )
                    ],
                ),
            ),
        ],
    )
    def test_get_term_refund_policy_diff(self, mock_boto3, get_entity, custom_config, expected_diff):
        entity1, entity2 = get_entity
        setattr(entity2, "Terms", custom_config)
        assert entity1.get_diff(entity2) == expected_diff

    @pytest.mark.parametrize(
        "index, custom_config, expected_diff",
        [
            (
                1,
                {
                    "Type": "UsageBasedPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "0.004"},
                            ]
                        }
                    ],
                },
                models.DiffModel(
                    added=[],
                    removed=[
                        models.DiffRemovedModel(
                            name="UsageBasedPricingTerm", value={"DimensionKey": "a1.xlarge", "Price": "0.007"}
                        ),
                    ],
                    changed=[],
                ),
            ),
            (
                2,
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "Selector": {"Type": "Duration", "Value": "P365D"},
                            "Constraints": {
                                "MultipleDimensionSelection": "Allowed",
                                "QuantityConfiguration": "Allowed",
                            },
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "24.528"},
                                {"DimensionKey": "a1.xlarge", "Price": "80.0"},
                            ],
                        }
                    ],
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="ConfigurableUpfrontPricingTerm",
                            old_value={"DimensionKey": "a1.xlarge", "Price": "49.056"},
                            new_value={"DimensionKey": "a1.xlarge", "Price": "80.0"},
                        ),
                    ],
                ),
            ),
            (
                2,
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "Selector": {"Type": "Duration", "Value": "P200D"},
                            "Constraints": {
                                "MultipleDimensionSelection": "Allowed",
                                "QuantityConfiguration": "Allowed",
                            },
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "24.528"},
                                {"DimensionKey": "a1.xlarge", "Price": "49.056"},
                            ],
                        }
                    ],
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="ConfigurableUpfrontPricingTerm",
                            old_value={"Type": "Duration", "Value": "P365D"},
                            new_value={"Type": "Duration", "Value": "P200D"},
                        )
                    ],
                ),
            ),
            (
                2,
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "Selector": {"Type": "Duration", "Value": "P365D"},
                            "Constraints": {
                                "MultipleDimensionSelection": "Allowed",
                                "QuantityConfiguration": "Disallowed",
                            },
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "24.528"},
                                {"DimensionKey": "a1.xlarge", "Price": "49.056"},
                            ],
                        }
                    ],
                },
                models.DiffModel(
                    added=[],
                    removed=[],
                    changed=[
                        models.DiffChangedModel(
                            name="ConfigurableUpfrontPricingTerm",
                            old_value={"MultipleDimensionSelection": "Allowed", "QuantityConfiguration": "Allowed"},
                            new_value={"MultipleDimensionSelection": "Allowed", "QuantityConfiguration": "Disallowed"},
                        )
                    ],
                ),
            ),
        ],
    )
    def test_get_term_pricing_diff(self, mock_boto3, get_entity, index, custom_config, expected_diff):
        entity1, entity2 = get_entity
        entity2.Terms[index] = custom_config
        assert entity1.get_diff(entity2) == expected_diff

    @pytest.mark.parametrize(
        "key, value",
        [
            ("refund_policy", "test_refund_policy_term\n"),
            (
                "instance_types",
                [
                    {"name": "a1.large", "hourly": "0.004", "yearly": "24.528"},
                    {"name": "a1.xlarge", "hourly": "0.007", "yearly": "49.056"},
                ],
            ),
            ("eula_document", [{"type": ""}]),
        ],
    )
    def test_convert_terms_to_dict(self, mock_boto3, get_entity, key, value):
        entity, _ = get_entity
        yaml_config = entity._convert_terms_to_dict()
        assert yaml_config[key] == value


class TestPromotionalResourcesModel:
    def test_get_promotional_resources_videos(self):
        res = models.PromotionalResourcesModel(
            LogoUrl=HttpUrl(
                "https://test-logourl"
            ),  # mypy error since it doesn't recognize the pydantic convert at runtime
            Videos=[{"Type": "Link", "Title": "Product Video", "Url": "https://video-url"}],
            AdditionalResources=[{"Text": "test-link", "Url": "https://test-url/"}],
        )
        assert res.Videos[0] == HttpUrl("https://video-url")

    def test_get_promotional_resources_videos_empty(self):
        res = models.PromotionalResourcesModel(
            LogoUrl=HttpUrl(
                "https://test-logourl"
            ),  # mypy error since it doesn't recognize the pydantic convert at runtime
            Videos=[],
            AdditionalResources=[{"Text": "test-link", "Url": "https://test-url/"}],
        )
        assert res.Videos == []

    def test_get_promotional_resources_invalid_videos(self):
        with pytest.raises(ValidationError):
            models.PromotionalResourcesModel(
                LogoUrl=HttpUrl(
                    "https://test-logourl"
                ),  # mypy error since it doesn't recognize the pydantic convert at runtime
                Videos=["url"],  # type: ignore
                AdditionalResources=[{"Text": "test-link", "Url": "https://test-url/"}],
            )

    @pytest.mark.parametrize(
        "key, value",
        [
            ("logo_url", "https://test.logo.url/"),
            ("video_urls", ["https://test.video.url/"]),
            ("additional_resources", [{"test": "https://resources.url/"}]),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.PromotionalResourcesModel(
            LogoUrl=HttpUrl(
                "https://test.logo.url/"
            ),  # mypy error since it doesn't recognize the pydantic convert at runtime
            Videos=[{"Type": "Link", "Title": "Product Video", "Url": "https://test.video.url/"}],
            AdditionalResources=[{"Text": "test", "Url": "https://resources.url"}],
        ).to_dict()
        assert yaml_config[key] == value


class TestOperatingSystemModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("os_system_name", "UBUNTU"),
            ("os_user_name", "ubuntu"),
            ("os_system_version", "22.04 - Jammy"),
            ("scanning_port", 22),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.OperatingSystemModel(
            Name="UBUNTU", Version="22.04 - Jammy", Username="ubuntu", ScanningPort=22
        ).to_dict()
        assert yaml_config[key] == value


class TestSourcesModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("ami_id", "ami-123456789"),
            ("os_system_name", "UBUNTU"),
            ("os_user_name", "ubuntu"),
            ("os_system_version", "22.04 - Jammy"),
            ("scanning_port", 22),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.SourcesModel(
            Image="ami-123456789",
            OperatingSystem=models.OperatingSystemModel(
                Name="UBUNTU", Version="22.04 - Jammy", Username="ubuntu", ScanningPort=22
            ),
        ).to_dict()
        assert yaml_config[key] == value


class TestSecurityGroupsModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("ip_protocol", "tcp"),
            ("ip_ranges", ["0.0.0.0/0"]),
            ("from_port", 22),
            ("to_port", 22),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.SecurityGroupsModel(
            Protocol="tcp", FromPort=22, ToPort=22, CidrIps=["0.0.0.0/0"]
        ).to_dict()
        assert yaml_config[key] == value


class TestRecommendationsModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("recommended_instance_types", "t1.micro"),
            ("ip_protocol", "tcp"),
            ("ip_ranges", ["0.0.0.0/0"]),
            ("from_port", 22),
            ("to_port", 22),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.RecommendationsModel(
            InstanceType="t1.micro",
            SecurityGroups=[models.SecurityGroupsModel(Protocol="tcp", FromPort=22, ToPort=22, CidrIps=["0.0.0.0/0"])],
        ).to_dict()
        assert yaml_config[key] == value


class TestDeliveryMethodsModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("usage_instructions", "test usage instruction"),
            ("recommended_instance_types", "t1.micro"),
            ("ip_protocol", "tcp"),
            ("ip_ranges", ["0.0.0.0/0"]),
            ("from_port", 22),
            ("to_port", 22),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.DeliveryMethodsModel(
            Instructions={"Usage": "test usage instruction"},
            Recommendations=models.RecommendationsModel(
                InstanceType="t1.micro",
                SecurityGroups=[
                    models.SecurityGroupsModel(Protocol="tcp", FromPort=22, ToPort=22, CidrIps=["0.0.0.0/0"])
                ],
            ),
        ).to_dict()
        assert yaml_config[key] == value


class TestVersionModel:
    @pytest.fixture
    def get_versions(self):
        with open("./tests/test_config.json", "r") as f:
            response_json = json.load(f)
        return response_json["Versions"]

    def test_get_version_title(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.VersionTitle == "Test Ubuntu AMI"

    def test_get_release_notes(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.ReleaseNotes == "test release notes"

    def test_get_sources(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.Sources[0].Image == "ami-12345678910"

    def test_get_sources_operating_system(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.Sources[0].OperatingSystem.Name == "UBUNTU"
        assert version.Sources[0].OperatingSystem.Version == "22.04 - Jammy"
        assert version.Sources[0].OperatingSystem.Username == "ubuntu"
        assert version.Sources[0].OperatingSystem.ScanningPort == 22

    def test_get_delivery_methods(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.DeliveryMethods[0].Instructions["Usage"] == "test_usage_instruction\n"

    def test_get_delivery_methods_recommendations_instance_type(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.DeliveryMethods[0].Recommendations.InstanceType == "t3.medium"

    def test_get_delivery_methods_recommendations_security_groups(self, get_versions):
        version = models.VersionModel(**get_versions)
        assert version.DeliveryMethods[0].Recommendations.SecurityGroups[0].Protocol == "tcp"
        assert version.DeliveryMethods[0].Recommendations.SecurityGroups[0].FromPort == 22
        assert version.DeliveryMethods[0].Recommendations.SecurityGroups[0].ToPort == 22
        assert version.DeliveryMethods[0].Recommendations.SecurityGroups[0].CidrIps == ["0.0.0.0/0"]

    def test_invallid_operating_system_version(self, get_versions):
        get_versions["Sources"][0]["OperatingSystem"]["Version"] = 22.04
        with pytest.raises(ValidationError):
            models.VersionModel(**get_versions)

    def test_invallid_security_group_protocol(self, get_versions):
        get_versions["DeliveryMethods"][0]["Recommendations"]["SecurityGroups"][0] = "smtp"
        with pytest.raises(ValidationError):
            models.VersionModel(**get_versions)

        with pytest.raises(ValidationError):
            models.VersionModel(**get_versions)

    @pytest.mark.parametrize(
        "key, value",
        [
            ("version_title", "Test Ubuntu AMI"),
            ("release_notes", "test release notes"),
            ("usage_instructions", "test_usage_instruction\n"),
            ("recommended_instance_types", "t3.medium"),
            ("ip_protocol", "tcp"),
            ("ip_ranges", ["0.0.0.0/0"]),
            ("from_port", 22),
            ("to_port", 22),
            ("ami_id", "ami-12345678910"),
            ("os_system_name", "UBUNTU"),
            ("os_user_name", "ubuntu"),
            ("os_system_version", "22.04 - Jammy"),
            ("scanning_port", 22),
        ],
    )
    def test_to_dict(self, get_versions, key, value):
        yaml_config = models.VersionModel(**get_versions).to_dict()
        assert yaml_config[key] == value


class TestSupportInformationModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("support_description", "test description"),
            ("support_resources", ["test support resources"]),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.SupportInformationModel(
            Description="test description", Resources=["test support resources"]
        ).to_dict()
        assert yaml_config[key] == value


class TestRegionAvailabilityModel:
    @pytest.mark.parametrize(
        "key, value",
        [
            ("commercial_regions", ["us-east-1", "us-west-2"]),
            ("future_region_support", True),
        ],
    )
    def test_to_dict(self, key, value):
        yaml_config = models.RegionAvailabilityModel(
            Regions=["us-east-1", "us-west-2"], FutureRegionSupport="All"
        ).to_dict()
        assert yaml_config[key] == value

    @pytest.mark.parametrize(
        "key, value",
        [
            ("commercial_regions", ["us-east-1", "us-west-2"]),
            ("future_region_support", False),
        ],
    )
    def test_to_dict_future_region_not_enabled(self, key, value):
        yaml_config = models.RegionAvailabilityModel(
            Regions=["us-east-1", "us-west-2"], FutureRegionSupport="None"
        ).to_dict()
        assert yaml_config[key] == value
