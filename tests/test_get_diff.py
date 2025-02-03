import json

import pytest
import yaml
from pydantic import ValidationError

from awsmp import _driver, models


def test_valid_response():
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_full_ami_product_details.return_value = response_json

    entity_model = models.EntityModel(**response_json)
    assert entity_model.Description.ProductTitle == "test"


def test_yaml_to_entity():
    with open("./tests/test_config.yaml", "r") as f:
        local_config = yaml.safe_load(f)
    entity_model = models.EntityModel._get_entity_from_yaml(local_config)
    assert entity_model.Description.ProductTitle == "test"


def test_non_valid_response():
    non_valid_response = {
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
    "local_config_custom, expected_diff",
    [
        (
            {},
            {},
        ),
        (
            {
                "description": {"short_description": "test"},
            },
            {"ShortDescription": "test"},
        ),
        (
            {"description": {"long_description": "long_description", "highlights": ["highlight_temp"]}},
            {"LongDescription": "long_description", "Highlights": ["highlight_temp"]},
        ),
    ],
)
def test_diff_entity_get_description_diff(expected_diff, local_config_custom):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json

    with open("./tests/test_config.yaml", "r") as f:
        local_config = yaml.safe_load(f)

    for k, v in local_config_custom.items():
        for key, value in v.items():
            local_config[k][key] = value

    live_listing_entity = models.EntityModel(**response_json)
    local_listing_entity = models.EntityModel._get_entity_from_yaml(local_config)

    assert live_listing_entity._get_description_diff(local_listing_entity) == expected_diff


@pytest.mark.parametrize(
    "local_config_custom, expected_diff",
    [
        (
            {},
            {},
        ),
        (
            {
                "region": {
                    "future_region_support": False,
                }
            },
            {"FutureRegionSupport": "None"},
        ),
        (
            {
                "region": {
                    "commercial_regions": ["us-east-1", "us-west-1"],
                }
            },
            {"Regions": ["us-west-1"]},
        ),
    ],
)
def test_diff_entity_get_region_diff(expected_diff, local_config_custom):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json

    with open("./tests/test_config.yaml", "r") as f:
        local_config = yaml.safe_load(f)

    for k, v in local_config_custom.items():
        for key, value in v.items():
            local_config[k][key] = value

    live_listing_entity = models.EntityModel(**response_json)
    local_listing_entity = models.EntityModel._get_entity_from_yaml(local_config)

    assert live_listing_entity._get_region_diff(local_listing_entity) == expected_diff


@pytest.mark.parametrize(
    "local_config_custom, expected_diff",
    [
        (
            {},
            {},
        ),
        (
            {"refund_policy": "test_support_term"},
            {"SupportTerm": "test_support_term"},
        ),
    ],
)
def test_diff_entity_get_support_term_diff(expected_diff, local_config_custom):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json

    with open("./tests/test_config.yaml", "r") as f:
        local_config = yaml.safe_load(f)

    for k, v in local_config_custom.items():
        local_config[k] = v

    live_listing_entity = models.EntityModel(**response_json)
    local_listing_entity = models.EntityModel._get_entity_from_yaml(local_config)
    print(live_listing_entity._get_support_term_diff(local_listing_entity))

    assert live_listing_entity._get_support_term_diff(local_listing_entity) == expected_diff


# @pytest.mark.parametrize(
#    "local_ami_config, local_region_config, local_support_term, local_legal_term, expected_diff",
#    [
#        (
#            {
#                "product_title": "test",
#                "short_description": "test_short_description",
#                "long_description": "test_long_description",
#                "highlights": ["test_highlight_1"],
#                "logourl": "https://test-logourl",
#                "search_keywords": ["test_keyword_1"],
#                "support_description": "test_support_description",
#                "categories": ["Migration"],
#            },
#            {
#                "commercial_regions": ["us-east-1", "us-east-2"],
#                "future_region_support": True,
#            },
#            {"description": "test_support_description", "resources": ["test_support_resource"]},
#            "https://eula",
#            [{}, {}, {}],
#        ),
#        (
#            {
#                "product_title": "test",
#                "short_description": "test_short_description",
#                "long_description": "test_long_description",
#                "highlights": ["test_highlight_1"],
#                "logourl": "https://test-logourl",
#                "search_keywords": ["test_keyword_1"],
#                "support_description": "test_support_description",
#                "categories": ["Migration"],
#            },
#            {
#                "commercial_regions": ["us-east-1", "us-west-1"],
#                "future_region_support": True,
#            },
#            {"description": "test_support_description", "resources": ["test_support_resource"]},
#            "https://eula",
#            [{}, {"commercial_regions": ["us-west-1"]}, {}],
#        ),
#    ],
# )
# def test_diff_entity_get_diff(expected_diff, local_config):
#    with open("./tests/test_config.json", "r") as f:
#        response_json = json.load(f)
#    _driver.get_entity_details.return_value = response_json
#    entity = models.Entity(**response_json)
#
#    ami = models.AmiProduct(**local_ami_config)
#    ami_region = models.Region(**local_region_config)
#
#    assert entity.get_diff(ami, ami_region, local_support_term, local_legal_term) == expected_diff
#
