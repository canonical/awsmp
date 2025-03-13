import json
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from pydantic import HttpUrl, ValidationError

from awsmp import _driver, models



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
        product = build_ami_product(additional_resources=provided_keys)
        assert product.additional_resources == expected

    @pytest.mark.parametrize("ami_product_field", ["support_description", "long_description"])
    def test_should_strip_new_lines_from_relevent_fields(self, ami_product_field):
        valid_description = "my description\n\nafter separator"
        product = build_ami_product(**{ami_product_field: f"\n\n\n{valid_description}\n\n"})
        assert getattr(product, ami_product_field) == valid_description

    def test_search_keywords_should_not_accept_large_input(self):
        keywords = ["a" * 150, "b" * 105, "c", "d", "e"]
        with pytest.raises(ValueError) as e:
            build_ami_product(search_keywords=keywords)
        err = "Combined character count of keywords can be at most 250 characters"
        assert err in str(e.value)


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

    @pytest.fixture
    def mock_boto3(self):
        with patch("awsmp.models.boto3") as mock_boto3:
            mock_boto3.client.return_value.describe_regions.return_value = {
                "Regions": [
                    {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
                    {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
                ]
            }
            yield mock_boto3

    def test_valid_response(self):
        with open("./tests/test_config.json", "r") as f:
            response_json = json.load(f)

        entity_model = models.EntityModel(**response_json)
        assert entity_model.Description.ProductTitle == "test"

    def test_yaml_to_entity(self, mock_boto3):
        with open("./tests/test_config.yaml", "r") as f:
            local_config = yaml.safe_load(f)

        entity_model = models.EntityModel.get_entity_from_yaml(local_config)
        assert entity_model.Description.ProductTitle == "test"

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
                        Videos=["https://video-url"],
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
