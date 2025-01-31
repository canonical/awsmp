import json

import pytest
from pydantic import ValidationError

from awsmp import _driver, models


def test_valid_response():
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json
    entity_model = models.Entity(**response_json)
    assert entity_model.Description.ProductTitle == "test"


#def test_non_valid_response():
#    non_valid_response = {
#        "Description": {
#            "ProductTitle": "test",
#            "ProductCode": "prod-test",
#        },
#        "PromotionalResources": {
#            "LogoUrl": "https://test-logourl",
#        },
#        "RegionAvailability": {"FutureRegionSupport": "All", "Restrict": [], "Regions": ["us-east-1", "us-east-2"]},
#        "SupportInformation": {"Description": "test_support_description", "Resources": ["test_support_resource"]},
#        "Versions": {"version1": ""},
#    }
#    with pytest.raises(ValidationError):
#        models.Entity(**non_valid_response)


@pytest.mark.parametrize(
    "local_config, expected_diff",
    [
        (
            {
                "product_title": "test",
                "short_description": "test_short_description",
                "long_description": "test_long_description",
                "highlights": ["test_highlight_1"],
                "logourl": "https://test-logourl",
                "search_keywords": ["test_keyword_1"],
                "support_description": "test_support_description",
                "categories": ["Migration"],
            },
            {},
        ),
        (
            {
                "product_title": "test",
                "short_description": "test",
                "long_description": "test_long_description",
                "highlights": ["test_highlight_1"],
                "logourl": "https://test-logourl",
                "search_keywords": ["test_keyword_1"],
                "support_description": "test_support_description",
                "categories": ["Migration"],
            },
            {"short_description": "test"},
        ),
        (
            {
                "product_title": "test",
                "short_description": "test_short_description",
                "long_description": "long_description",
                "highlights": ["highlight_1"],
                "logourl": "https://test-logourl",
                "search_keywords": ["test_keyword_1"],
                "support_description": "test_support_description",
                "categories": ["Migration"],
            },
            {"long_description": "long_description", "highlights": ["highlight_1"]},
        ),
    ],
)
def test_diff_entity_get_description_diff(expected_diff, local_config):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json

    entity = models.Entity(**response_json)
    ami = models.AmiProduct(**local_config)

    assert entity._get_description_diff(ami) == expected_diff


@pytest.mark.parametrize(
    "local_config, expected_diff",
    [
        (
            {
                "commercial_regions": ["us-east-1", "us-east-2"],
                "future_region_support": True,
            },
            {},
        ),
        (
            {
                "commercial_regions": ["us-east-1", "us-east-2"],
                "future_region_support": False,
            },
            {"future_region_support": ["None"]},
        ),
        (
            {
                "commercial_regions": ["us-east-1", "us-west-1"],
                "future_region_support": True,
            },
            {"commercial_regions": ["us-west-1"]},
        ),
    ],
)
def test_diff_entity_get_region_diff(expected_diff, local_config):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json

    entity = models.Entity(**response_json)
    ami_region = models.Region(**local_config)

    assert entity._get_region_diff(ami_region) == expected_diff


@pytest.mark.parametrize(
    "local_legal_term, local_support_term, expected_diff",
    [
        (
            "https://eula",
            {"description": "test_support_description", "resources": ["test_support_resource"]},
            {},
        ),
        (
            "https://eula",
            {"description": "test_local_description", "resources": ["test_support_resource"]},
            {"description": "test_local_description"},
        ),
    ],
)
def test_diff_entity_get_support_and_legal_diff(expected_diff, local_support_term, local_legal_term):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json
    entity = models.Entity(**response_json)

    assert (
        entity._get_support_and_legal_diff(local_support_term, local_legal_term) == expected_diff
    )


@pytest.mark.parametrize(
    "local_ami_config, local_region_config, local_support_term, local_legal_term, expected_diff",
    [
        (
            {
                "product_title": "test",
                "short_description": "test_short_description",
                "long_description": "test_long_description",
                "highlights": ["test_highlight_1"],
                "logourl": "https://test-logourl",
                "search_keywords": ["test_keyword_1"],
                "support_description": "test_support_description",
                "categories": ["Migration"],
            },
            {
                "commercial_regions": ["us-east-1", "us-east-2"],
                "future_region_support": True,
            },
            {"description": "test_support_description", "resources": ["test_support_resource"]},
            "https://eula",
            [{}, {}, {}],
        ),
        (
            {
                "product_title": "test",
                "short_description": "test_short_description",
                "long_description": "test_long_description",
                "highlights": ["test_highlight_1"],
                "logourl": "https://test-logourl",
                "search_keywords": ["test_keyword_1"],
                "support_description": "test_support_description",
                "categories": ["Migration"],
            },
            {
                "commercial_regions": ["us-east-1", "us-west-1"],
                "future_region_support": True,
            },
            {"description": "test_support_description", "resources": ["test_support_resource"]},
            "https://eula",
            [{}, {"commercial_regions": ["us-west-1"]}, {}],
        ),
    ],
)
def test_diff_entity_get_diff(expected_diff, local_legal_term, local_support_term, local_region_config, local_ami_config):
    with open("./tests/test_config.json", "r") as f:
        response_json = json.load(f)
    _driver.get_entity_details.return_value = response_json
    entity = models.Entity(**response_json)
    
    ami = models.AmiProduct(**local_ami_config)
    ami_region = models.Region(**local_region_config)

    assert entity.get_diff(ami, ami_region, local_support_term, local_legal_term) == expected_diff

