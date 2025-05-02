import io
from typing import List, cast
from unittest.mock import patch

import pytest
import yaml
from botocore.exceptions import ClientError
from pydantic import ValidationError

from awsmp import _driver
from awsmp.errors import (
    AccessDeniedException,
    AmiPriceChangeError,
    MissingInstanceTypeError,
    ResourceNotFoundException,
    UnrecognizedClientException,
)
from awsmp.types import ChangeSetType


class TestAmiProduct(object):
    """Tests to validate AmiProduct"""

    @patch("awsmp._driver.get_public_offer_id")
    def test_ami_product_class(self, mock_get_public_offer_id):
        mock_get_public_offer_id.return_value = "fake-offer-id"
        test_ami_product = _driver.AmiProduct(product_id="fake")
        assert test_ami_product.product_id == "fake"
        assert test_ami_product.offer_id == "fake-offer-id"


@pytest.mark.parametrize(
    "args,expected",
    [
        (["123", ["456", "543"], True, "Name"], "Offer - 456,543 - Product XX.YY wSupport - Name"),
        (["123", ["12345678", "09876543"], False, "Name"], "Offer - 12345678,09876543 - Product XX.YY - Name"),
        (
            [
                "123",
                ["123"],
                False,
                "Really long name that should end up being truncated " + "o" * 100,
            ],
            "Offer - 123 - Product XX.YY - Really long name that should end up being truncated " + "o" * 68,
        ),
        (
            ["123", ["12345678"] * 10, False, "Name"],
            "Offer - 12345678,12345678,12345678,12345678,12345678,12... - Product XX.YY - Name",
        ),
    ],
)
@patch("awsmp._driver.get_entity_details")
def test_create_offer_name(mock_get_details, args, expected):
    mock_get_details.return_value = {"Description": {"ProductTitle": "Product XX.YY"}}
    result = _driver.create_offer_name(*args)
    assert result == expected


@patch("awsmp._driver.get_entity_details")
def test_filter_instance_types(mock_get_details):
    mock_get_details.return_value = {"Dimensions": [{"Name": "foo"}, {"Name": "bar"}]}
    ratecards = {"RateCards": [{"RateCard": [{"DimensionKey": "foo"}, {"DimensionKey": "bar"}]}]}
    changeset = [
        None,
        None,
        None,
        {"DetailsDocument": {"Terms": [ratecards, ratecards]}},
    ]
    res = _driver._filter_instance_types("product-id", changeset)
    assert res == changeset


@patch("awsmp._driver.get_entity_details")
def test_filter_instance_types_missing_types(mock_get_details):
    mock_get_details.return_value = {"Dimensions": [{"Name": "foo"}, {"Name": "bar"}, {"Name": "baz"}]}
    ratecards = {"RateCards": [{"RateCard": [{"DimensionKey": "foo"}, {"DimensionKey": "bar"}]}]}
    changeset = [
        None,
        None,
        None,
        {"DetailsDocument": {"Terms": [ratecards, ratecards]}},
    ]
    with pytest.raises(MissingInstanceTypeError):
        _driver._filter_instance_types("product-id", changeset)


@pytest.mark.parametrize(
    "invalid_config",
    [
        ({"search_keywords": ["search1", "search2", "search3", "a" * 237]}),
        (
            {
                "categories": ["Operating Systems", "Application Servers", "somethingnotvalid"],
            }
        ),
    ],
)
@patch("awsmp._driver.get_client")
def test_ami_product_update_description_validation_failure(mock_get_client, invalid_config):
    mock_desc = {
        "product_title": "temp-listing",
        "logourl": "https://validurl",
        "video_urls": [],
        "short_description": "short_desc",
        "long_description": "long_desc",
        "highlights": ["hi1", "hi2", "hi3"],
        "search_keywords": [
            "search1",
            "search2",
            "search3",
        ],
        "categories": [
            "Operating Systems",
            "Application Servers",
        ],
        "additional_resources": [],
        "sku": None,
        "support_description": "",
    }
    mock_desc.update(invalid_config)
    with pytest.raises(ValidationError):
        _driver.AmiProduct(product_id="testing").update_description(mock_desc)


@patch("awsmp._driver.get_client")
def test_ami_product_update_description(mock_get_client):
    with open("./tests/description.yaml", "r") as f:
        config = yaml.safe_load(f)
    desc = config["product"]["description"]

    ap = _driver.AmiProduct(product_id="testing")
    ap.update_description(desc)
    mock_start_change_set = mock_get_client.return_value.start_change_set

    assert (
        mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]["LogoUrl"]
        == "https://awsmp-logos.s3.amazonaws.com/8350ae04bad5625623cc02c64eb8b0b5"
    )


@patch("awsmp._driver.get_client")
def test_ami_product_create(mock_get_client):
    _driver.AmiProduct.create()
    mock_start_change_set = mock_get_client.return_value.start_change_set

    assert mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["Entity"]["Type"] == "AmiProduct@1.0"


@patch("awsmp._driver.get_client")
def test_ami_product_create_with_wrong_credentials(mock_get_client):
    mock_get_client.side_effect = UnrecognizedClientException
    with pytest.raises(UnrecognizedClientException) as excInfo:
        _driver.AmiProduct.create()
    assert "This profile is not configured correctly" in excInfo.value.args[0]


@patch("awsmp._driver.get_client")
def test_ami_product_create_without_permission(mock_get_client):
    mock_get_client.side_effect = AccessDeniedException(service_name="marketplace")
    with pytest.raises(AccessDeniedException) as excInfo:
        _driver.AmiProduct.create()
    assert "This account does not have permission to request marketplace services" in excInfo.value.args[0]


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_ami_product_update_instance_type(mock_get_details, mock_get_client):
    ap = _driver.AmiProduct(product_id="testing")
    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.00"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    offer_config = {
        "instance_types": [
            {"name": "c3.2xlarge", "hourly": 0.00, "yearly": 0.00},
            {"name": "c3.4xlarge", "hourly": 0.00, "yearly": 0.00},
            {"name": "c3.8xlarge", "hourly": 0.00, "yearly": 0.00},
            {"name": "c3.16xlarge", "hourly": 0.00, "yearly": 0.00},
        ],
        "refund_policy": "refund_policy",
        "eula_document": [{"type": "StandardEula", "version": "2025-04-05"}],
    }

    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }
    res = ap.update_instance_types(offer_config, False)

    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][2][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c3.16xlarge"]}
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"][
            "Terms"
        ][0]["RateCards"][0]["RateCard"][-1]["DimensionKey"]
        == "c3.16xlarge"
        and mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"][
            "Terms"
        ][0]["RateCards"][0]["RateCard"][-1]["Price"]
        == "0.0"
    )


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_ami_product_update_instance_type_restrict_instance_type(mock_get_details, mock_get_client):
    ap = _driver.AmiProduct(product_id="testing")
    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.00"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    mock_get_details.return_value = {
        "Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]
    }
    offer_config = {
        "instance_types": [
            {"name": "c3.2xlarge", "hourly": 0.00, "yearly": 0.00},
            {"name": "c3.4xlarge", "hourly": 0.00, "yearly": 0.00},
        ],
        "refund_policy": "refund_policy",
        "eula_document": [{"type": "StandardEula", "version": "2025-04-05"}],
    }
    res = ap.update_instance_types(offer_config, False)

    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][1][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c3.8xlarge"]}
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][2]["DetailsDocument"][
        0
    ] == {"Key": "c3.8xlarge", "Types": ["Metered"]}


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_ami_product_update_instance_type_restrict_and_add_instance_type(mock_get_details, mock_get_client):
    ap = _driver.AmiProduct(product_id="testing")
    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.00"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    offer_config = {
        "instance_types": [
            {"name": "c3.2xlarge", "hourly": 0.00, "yearly": 0.00},
            {"name": "c3.4xlarge", "hourly": 0.00, "yearly": 0.00},
            {"name": "c1.medium", "hourly": 0.00, "yearly": 0.00},
        ],
        "refund_policy": "refund_policy",
        "eula_document": [{"type": "StandardEula", "version": "2025-04-05"}],
    }
    res = ap.update_instance_types(offer_config, False)

    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][1]["DetailsDocument"][0][
            "Key"
        ]
        == "c1.medium"
    )
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][2][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c1.medium"]}
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][3][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c3.8xlarge"]}
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][4]["DetailsDocument"][
        0
    ] == {"Key": "c3.8xlarge", "Types": ["Metered"]}


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_ami_product_update_instance_type_pricing_update(mock_get_details, mock_get_client):
    ap = _driver.AmiProduct(product_id="testing")
    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.03"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.12"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.50"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "12.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "24.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "90.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    offer_config = {
        "instance_types": [
            {"name": "c3.2xlarge", "hourly": 0.03, "yearly": 12.00},
            {"name": "c3.4xlarge", "hourly": 0.12, "yearly": 24.00},
            {"name": "c3.8xlarge", "hourly": 0.50, "yearly": 78.00},
        ],
        "refund_policy": "refund_policy",
        "eula_document": [{"type": "StandardEula", "version": "2025-04-05"}],
    }

    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }
    res = ap.update_instance_types(offer_config, False)
    assert res == None


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_ami_product_update_instance_type_restrict_and_add_instance_type_pricing_update(
    mock_get_details, mock_get_client
):
    ap = _driver.AmiProduct(product_id="testing")
    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.03"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.12"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.50"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "12.00"},
                                {"DimensionKey": "c3.4xlarge", "Price": "24.00"},
                                {"DimensionKey": "c3.8xlarge", "Price": "90.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    offer_config = {
        "instance_types": [
            {"name": "c3.2xlarge", "hourly": 0.03, "yearly": 12.00},
            {"name": "c3.4xlarge", "hourly": 0.12, "yearly": 28.00},
            {"name": "c1.medium", "hourly": 0.04, "yearly": 10.00},
        ],
        "refund_policy": "refund_policy",
        "eula_document": [{"type": "StandardEula", "version": "2025-04-05"}],
    }
    res = ap.update_instance_types(offer_config, True)

    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][1]["DetailsDocument"][0][
            "Key"
        ]
        == "c1.medium"
    )
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][2][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c1.medium"]}
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][3][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c3.8xlarge"]}
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][4]["DetailsDocument"][
        0
    ] == {"Key": "c3.8xlarge", "Types": ["Metered"]}
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"][
            "Terms"
        ][1]["RateCards"][0]["RateCard"][1]["Price"]
        == "28.0"
    )


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_ami_product_update_instance_type_pricing_update_exception(mock_get_details, mock_get_client):
    ap = _driver.AmiProduct(product_id="testing")
    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.2xlarge", "Price": "0.03"},
                                {"DimensionKey": "c3.4xlarge", "Price": "0.12"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.50"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    offer_config = {
        "instance_types": [
            {"name": "c3.2xlarge", "hourly": 0.03, "yearly": 12.00},
            {"name": "c3.4xlarge", "hourly": 0.12, "yearly": 28.00},
            {"name": "c3.8xlarge", "hourly": 0.50, "yearly": 75.00},
        ],
        "refund_policy": "refund_policy",
        "eula_document": [{"type": "StandardEula", "version": "2025-04-05"}],
    }
    with pytest.raises(AmiPriceChangeError) as excInfo:
        ap.update_instance_types(offer_config, True)
    assert "Contact AWS Marketplace" in excInfo.value.args[0]


@pytest.mark.parametrize(
    "terms, expected_output",
    [
        (
            [
                {
                    "Type": "UsageBasedPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                            ]
                        }
                    ],
                },
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
                                {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                                {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                            ],
                        }
                    ],
                },
                {"Type": "LegalTerm", "Documents": [{"Type": "CustomEula", "Url": "https://aws.com"}]},
                {"Type": "SupportTerm", "RefundPolicy": "No refunds.\n"},
            ],
            (
                [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}, {"DimensionKey": "c3.8xlarge", "Price": "0.056"}],
                [
                    {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                    {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                ],
            ),
        ),
        (
            [
                {
                    "Type": "UsageBasedPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                            ]
                        }
                    ],
                },
                {"Type": "LegalTerm", "Documents": [{"Type": "CustomEula", "Url": "https://aws.com"}]},
                {"Type": "SupportTerm", "RefundPolicy": "No refunds.\n"},
            ],
            ([{"DimensionKey": "c3.4xlarge", "Price": "0.028"}, {"DimensionKey": "c3.8xlarge", "Price": "0.056"}], []),
        ),
        (
            [
                {"Type": "LegalTerm", "Documents": [{"Type": "CustomEula", "Url": "https://aws.com"}]},
                {"Type": "SupportTerm", "RefundPolicy": "No refunds.\n"},
            ],
            ([], []),
        ),
    ],
)
def test_get_full_ratecard_info(terms, expected_output):
    assert _driver._get_full_ratecard_info(terms) == expected_output


@pytest.mark.parametrize(
    "existing_prices, local_prices, expected_diffs",
    [
        ([], [], []),
        (
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}, {"DimensionKey": "c3.8xlarge", "Price": "0.056"}],
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}, {"DimensionKey": "c3.8xlarge", "Price": "0.12"}],
            [{"DimensionKey": "c3.8xlarge", "Original Price": "0.056", "New Price": "0.12"}],
        ),
        (
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}, {"DimensionKey": "c3.8xlarge", "Price": "0.056"}],
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}],
            [],
        ),
        (
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}],
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}, {"DimensionKey": "c3.8xlarge", "Price": "0.056"}],
            [],
        ),
        (
            [{"DimensionKey": "c3.4xlarge", "Price": "0.028"}],
            [{"DimensionKey": "c3.4xlarge", "Price": "0.012"}, {"DimensionKey": "c3.8xlarge", "Price": "0.056"}],
            [{"DimensionKey": "c3.4xlarge", "Original Price": "0.028", "New Price": "0.012"}],
        ),
    ],
)
def test_build_pricing_diff(existing_prices, local_prices, expected_diffs):
    assert _driver._build_pricing_diff(existing_prices, local_prices) == expected_diffs


@pytest.mark.parametrize(
    "visibility, terms, changeset, expected_output",
    [
        ("Draft", {"Terms": []}, [{"ChangeType": "UpdatePricingTerms", "DetailsDocument": {"Terms": []}}], ([], [])),
        (
            "Draft",
            {"Terms": []},
            [
                {
                    "ChangeType": "UpdatePricingTerms",
                    "DetailsDocument": {
                        "PricingModel": "Usage",
                        "Terms": [
                            {
                                "Type": "UsageBasedPricingTerm",
                                "CurrencyCode": "USD",
                                "RateCards": [
                                    {
                                        "RateCard": [
                                            {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                        ]
                                    }
                                ],
                            },
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
                                            {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                }
            ],
            ([], []),
        ),
        (
            "Draft",
            {
                "Terms": [
                    {
                        "Type": "UsageBasedPricingTerm",
                        "CurrencyCode": "USD",
                        "RateCards": [
                            {
                                "RateCard": [
                                    {"DimensionKey": "c3.4xlarge", "Price": "0.0"},
                                    {"DimensionKey": "c3.8xlarge", "Price": "0.0"},
                                ]
                            }
                        ],
                    }
                ]
            },
            [
                {
                    "ChangeType": "UpdatePricingTerms",
                    "DetailsDocument": {
                        "PricingModel": "Usage",
                        "Terms": [
                            {
                                "Type": "UsageBasedPricingTerm",
                                "CurrencyCode": "USD",
                                "RateCards": [
                                    {
                                        "RateCard": [
                                            {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                        ]
                                    }
                                ],
                            },
                        ],
                    },
                }
            ],
            (
                [
                    {"DimensionKey": "c3.4xlarge", "Original Price": "0.0", "New Price": "0.028"},
                    {"DimensionKey": "c3.8xlarge", "Original Price": "0.0", "New Price": "0.056"},
                ],
                [],
            ),
        ),
        (
            "Draft",
            {
                "Terms": [
                    {
                        "Type": "UsageBasedPricingTerm",
                        "CurrencyCode": "USD",
                        "RateCards": [
                            {
                                "RateCard": [
                                    {"DimensionKey": "c3.4xlarge", "Price": "0.0"},
                                    {"DimensionKey": "c3.8xlarge", "Price": "0.0"},
                                ]
                            }
                        ],
                    }
                ]
            },
            [
                {
                    "ChangeType": "UpdatePricingTerms",
                    "DetailsDocument": {
                        "Terms": [
                            {
                                "Type": "UsageBasedPricingTerm",
                                "RateCards": [
                                    {
                                        "RateCard": [
                                            {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                        ]
                                    }
                                ],
                            },
                        ],
                    },
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                                {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                            ]
                        }
                    ],
                },
            ],
            (
                [
                    {"DimensionKey": "c3.4xlarge", "Original Price": "0.0", "New Price": "0.028"},
                    {"DimensionKey": "c3.8xlarge", "Original Price": "0.0", "New Price": "0.056"},
                ],
                [],
            ),
        ),
        (
            "Limited",
            {
                "Terms": [
                    {
                        "Type": "UsageBasedPricingTerm",
                        "CurrencyCode": "USD",
                        "RateCards": [
                            {
                                "RateCard": [
                                    {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                    {"DimensionKey": "c3.8xlarge", "Price": "0.030"},
                                ]
                            }
                        ],
                    }
                ]
            },
            [
                {
                    "ChangeType": "UpdatePricingTerms",
                    "DetailsDocument": {
                        "Terms": [
                            {
                                "Type": "UsageBasedPricingTerm",
                                "RateCards": [
                                    {
                                        "RateCard": [
                                            {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                        ]
                                    }
                                ],
                            },
                        ],
                    },
                }
            ],
            (
                [
                    {"DimensionKey": "c3.8xlarge", "Original Price": "0.030", "New Price": "0.056"},
                ],
                [],
            ),
        ),
        (
            "Limited",
            {
                "Terms": [
                    {
                        "Type": "UsageBasedPricingTerm",
                        "RateCards": [
                            {
                                "RateCard": [
                                    {"DimensionKey": "c3.4xlarge", "Price": "0.012"},
                                    {"DimensionKey": "c3.8xlarge", "Price": "0.030"},
                                ]
                            }
                        ],
                    },
                    {
                        "Type": "ConfigurableUpfrontPricingTerm",
                        "RateCards": [
                            {
                                "RateCard": [
                                    {"DimensionKey": "c3.4xlarge", "Price": "13.0"},
                                    {"DimensionKey": "c3.8xlarge", "Price": "24.0"},
                                ]
                            }
                        ],
                    },
                ]
            },
            [
                {
                    "ChangeType": "UpdatePricingTerms",
                    "DetailsDocument": {
                        "Terms": [
                            {
                                "Type": "UsageBasedPricingTerm",
                                "RateCards": [
                                    {
                                        "RateCard": [
                                            {"DimensionKey": "c3.4xlarge", "Price": "0.012"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "0.028"},
                                        ]
                                    }
                                ],
                            },
                            {
                                "Type": "ConfigurableUpfrontPricingTerm",
                                "RateCards": [
                                    {
                                        "RateCard": [
                                            {"DimensionKey": "c3.4xlarge", "Price": "13.0"},
                                            {"DimensionKey": "c3.8xlarge", "Price": "56.00"},
                                        ]
                                    }
                                ],
                            },
                        ],
                    },
                },
            ],
            (
                [
                    {"DimensionKey": "c3.8xlarge", "Original Price": "0.030", "New Price": "0.028"},
                ],
                [{"DimensionKey": "c3.8xlarge", "Original Price": "24.0", "New Price": "56.00"}],
            ),
        ),
    ],
)
@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_get_pricing_diff(mock_get_entity_details, mock_get_client, visibility, terms, changeset, expected_output):
    mock_get_entity_details.side_effect = [{"Description": {"Visibility": visibility}}, terms]
    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }
    assert _driver._get_pricing_diff("prod-id", changeset) == expected_output


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_get_pricing_diff_exception(mock_get_entity_details, mock_get_client):
    mock_get_entity_details.side_effect = [
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]
    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }
    changeset = cast(
        List[ChangeSetType],
        [
            {
                "ChangeType": "UpdatePricingTerms",
                "Entity": {"Type": "Offer@1.0", "Identifier": "test-offer"},
                "DetailsDocument": {
                    "PricingModel": "Usage",
                    "Terms": [
                        {
                            "Type": "UsageBasedPricingTerm",
                            "CurrencyCode": "USD",
                            "RateCards": [
                                {
                                    "RateCard": [
                                        {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                        {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                    ]
                                }
                            ],
                        },
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
                                        {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                                        {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                                    ],
                                }
                            ],
                        },
                    ],
                },
            }
        ],
    )
    with pytest.raises(AmiPriceChangeError) as excInfo:
        _driver._get_pricing_diff("prod-id", changeset)
    assert "Contact AWS Marketplace" in excInfo.value.args[0]


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_get_pricing_diff_exception_no_yearly(mock_get_entity_details, mock_get_client):
    mock_get_entity_details.side_effect = [
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                            ]
                        }
                    ],
                },
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
                                {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                                {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                            ],
                        }
                    ],
                },
            ]
        },
    ]
    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }
    changeset = cast(
        List[ChangeSetType],
        [
            {
                "ChangeType": "UpdatePricingTerms",
                "Entity": {"Type": "Offer@1.0", "Identifier": "test-offer"},
                "DetailsDocument": {
                    "PricingModel": "Usage",
                    "Terms": [
                        {
                            "Type": "UsageBasedPricingTerm",
                            "CurrencyCode": "USD",
                            "RateCards": [
                                {
                                    "RateCard": [
                                        {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                        {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                    ]
                                }
                            ],
                        },
                    ],
                },
            }
        ],
    )
    with pytest.raises(AmiPriceChangeError) as excInfo:
        _driver._get_pricing_diff("prod-id", changeset)
    assert "Contact AWS Marketplace" in excInfo.value.args[0]


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
def test_get_pricing_diff_exception_free_to_paid(mock_get_entity_details, mock_get_client):
    mock_get_entity_details.side_effect = [
        {"Description": {"Visibility": "Public"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "c3.4xlarge", "Price": "0.0"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.0"},
                            ]
                        }
                    ],
                },
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
                                {"DimensionKey": "c3.4xlarge", "Price": "0.0"},
                                {"DimensionKey": "c3.8xlarge", "Price": "0.0"},
                            ],
                        }
                    ],
                },
            ]
        },
    ]
    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }
    changeset = cast(
        List[ChangeSetType],
        [
            {
                "ChangeType": "UpdatePricingTerms",
                "Entity": {"Type": "Offer@1.0", "Identifier": "test-offer"},
                "DetailsDocument": {
                    "PricingModel": "Usage",
                    "Terms": [
                        {
                            "Type": "UsageBasedPricingTerm",
                            "CurrencyCode": "USD",
                            "RateCards": [
                                {
                                    "RateCard": [
                                        {"DimensionKey": "c3.4xlarge", "Price": "0.028"},
                                        {"DimensionKey": "c3.8xlarge", "Price": "0.056"},
                                    ]
                                }
                            ],
                        },
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
                                        {"DimensionKey": "c3.4xlarge", "Price": "196.224"},
                                        {"DimensionKey": "c3.8xlarge", "Price": "392.448"},
                                    ],
                                }
                            ],
                        },
                    ],
                },
            }
        ],
    )
    with pytest.raises(AmiPriceChangeError) as excInfo:
        _driver._get_pricing_diff("prod-id", changeset)
    assert "Contact AWS Marketplace" in excInfo.value.args[0]


@pytest.mark.parametrize(
    "invalid_region_configs",
    [
        ({"commercial_regions": ["us-east-1", "us-east-2", "ca-east-4"]}),
        ({"future_region_support": None}),
        ({"commercial_regions": ["aLL"]}),
    ],
)
@patch("awsmp._driver.get_client")
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update_region_invalid_values(mock_boto3, mock_get_client, invalid_region_configs):
    mock_region_config = {
        "commercial_regions": ["eu-north-1"],
        "future_region_support": True,
    }
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.eu-north-1.amazonaws.com", "RegionName": "eu-north-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    mock_region_config.update(invalid_region_configs)

    with pytest.raises(ValidationError):
        _driver.AmiProduct(product_id="testing").update_regions(mock_region_config)


@pytest.mark.parametrize(
    "valid_region_configs",
    [
        ({"future_region_support": True}),
        ({"commercial_regions": ["all"]}),
    ],
)
@patch("awsmp._driver.get_client")
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update_region_valid_values(mock_boto3, mock_get_client, valid_region_configs):
    mock_region_config = {
        "commercial_regions": ["eu-north-1"],
        "future_region_support": True,
    }
    mock_region_config.update(valid_region_configs)
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [{"Endpoint": "ec2.eu-north-1.amazonaws.com", "RegionName": "eu-north-1", "OptInStatus": "opted-in"}]
    }
    ap = _driver.AmiProduct(product_id="testing")
    ap.update_regions(mock_region_config)

    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0][
        "DetailsDocument"
    ] == {"Regions": ["eu-north-1"]}
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][1][
        "DetailsDocument"
    ] == {"FutureRegionSupport": {"SupportedRegions": ["All"]}}


@pytest.mark.parametrize(
    "invalid_version_configs",
    [
        ({"scanning_port": 68888}),
        ({"access_role_arn": "arn:aws:missingiamrole"}),
        ({"ip_protocol": ["invalid_protocol"]}),
    ],
)
@patch("awsmp._driver.get_client")
def test_ami_product_update_version_invalid_values(mock_get_client, invalid_version_configs):
    mock_version_configs = {
        "version_title": "testing",
        "release_notes": "testing release note",
        "ami_id": "ami-sample",
        "os_user_name": "testing",
        "os_system_name": "testing system",
        "os_system_version": "testing version",
        "scanning_port": 22,
        "usage_instructions": "sample instruction",
        "recommended_instance_type": "testing.micro",
        "ip_protocol": "tcp",
        "ip_ranges": [
            "0.0.0.0/0",
        ],
        "from_port": 22,
        "to_port": 22,
        "access_role_arn": "arn:aws:iam::testingrole",
    }
    mock_version_configs.update(invalid_version_configs)

    with pytest.raises(ValidationError):
        _driver.AmiProduct(product_id="testing").update_version(mock_version_configs)


@patch("awsmp._driver.get_client")
def test_ami_product_update_version(mock_get_client):
    mock_version_config = {
        "version_title": "testing",
        "release_notes": "testing release note",
        "ami_id": "ami-sample",
        "os_user_name": "testing",
        "os_system_name": "testing system",
        "os_system_version": "testing version",
        "scanning_port": 22,
        "usage_instructions": "sample instruction",
        "recommended_instance_type": "testing.micro",
        "ip_protocol": "tcp",
        "ip_ranges": [
            "0.0.0.0/0",
        ],
        "from_port": 22,
        "to_port": 22,
        "access_role_arn": "arn:aws:iam::testingrole",
    }
    ap = _driver.AmiProduct(product_id="testing")
    ap.update_version(mock_version_config)

    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert {
        "AmiId": "ami-sample",
        "AccessRoleArn": "arn:aws:iam::testingrole",
        "UserName": "testing",
        "OperatingSystemName": "TESTING SYSTEM",
        "OperatingSystemVersion": "testing version",
        "ScanningPort": 22,
    } == mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"][
        "DeliveryOptions"
    ][
        0
    ][
        "Details"
    ][
        "AmiDeliveryOptionDetails"
    ][
        "AmiSource"
    ]


@patch("awsmp._driver.get_client")
def test_ami_product_update_legal_terms(mock_get_client):
    mock_eula = {"type": "CustomEula", "url": "https://testing-eula"}

    ap = _driver.AmiProduct(product_id="testing")
    ap.update_legal_terms(eula_document=mock_eula)
    assert {
        "Type": "CustomEula",
        "Url": "https://testing-eula",
    } == mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"][
        "Terms"
    ][
        0
    ][
        "Documents"
    ][
        0
    ]


@patch("awsmp._driver.get_client")
def test_ami_product_update_invalid_legal_terms(mock_get_client):
    mock_eula = {"type": "CustomEula", "version": "2022-05-06"}
    ap = _driver.AmiProduct(product_id="testing")
    with pytest.raises(ValidationError) as e:
        ap.update_legal_terms(eula_document=mock_eula)
    assert "can't pass version of standard document" in str(e.value)


@patch("awsmp._driver.get_client")
def test_ami_product_update_support_terms(mock_get_client):
    mock_refund_policy = "testing is not refundable"
    ap = _driver.AmiProduct(product_id="testing")
    ap.update_support_terms(refund_policy=mock_refund_policy)

    assert {
        "Terms": [{"Type": "SupportTerm", "RefundPolicy": "testing is not refundable"}]
    } == mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]


@patch("awsmp._driver.get_client")
def test_ami_product_release(mock_get_client):
    ap = _driver.AmiProduct(product_id="testing")
    ap.release()

    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["ChangeType"]
        == "ReleaseProduct"
    )
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["Entity"]["Type"]
        == "AmiProduct@1.0"
    )
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][1]["Entity"]["Type"]
        == "Offer@1.0"
    )


@patch("awsmp._driver.get_entity_details")
def test_get_entity_versions(mock_get_details):
    mock_get_details.return_value = {"Versions": [{"CreationDate": "20231010"}, {"CreationDate": "20230202"}]}
    assert _driver.get_entity_versions("foo") == [{"CreationDate": "20230202"}, {"CreationDate": "20231010"}]


@patch("awsmp._driver.get_client")
def test_get_public_offer_id(mock_get_client):
    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "testing-public-offer-id"}]
    }
    assert _driver.get_public_offer_id("testing") == "testing-public-offer-id"


@patch("awsmp._driver.get_client")
def test_get_public_no_offer_id(mock_get_client):
    mock_get_client.return_value.list_entities.return_value = {"EntitySummaryList": []}
    with pytest.raises(ResourceNotFoundException):
        _driver.get_public_offer_id("no-offer-id")


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update(mock_boto3, mock_get_details, mock_get_client):
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [{"Dimensions": []}, {"Description": {"Visibility": "Draft"}}, {"Terms": []}]

    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }

    ap = _driver.AmiProduct(product_id="testing")
    ap.update(config, False)
    mock_start_change_set = mock_get_client.return_value.start_change_set

    assert (
        "https://test-logourl"
        == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]["LogoUrl"]
    )
    assert {"Regions": ["us-east-1", "us-east-2"]} == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][1][
        "DetailsDocument"
    ]


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update_pricing_change(mock_boto3, mock_get_details, mock_get_client):
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "0.004"},
                                {"DimensionKey": "a1.xlarge", "Price": "0.007"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "24.528"},
                                {"DimensionKey": "a1.xlarge", "Price": "50.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }

    ap = _driver.AmiProduct(product_id="testing")
    res = ap.update(config, False)

    assert res == None


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update_pricing_exception_by_adding_yearly_price(mock_boto3, mock_get_details, mock_get_client):
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "0.004"},
                                {"DimensionKey": "a1.xlarge", "Price": "0.007"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }

    ap = _driver.AmiProduct(product_id="testing")

    with pytest.raises(AmiPriceChangeError) as excInfo:
        ap.update(config, False)

    assert "Contact AWS Marketplace" in excInfo.value.args[0]


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update_restrict_instance_types(mock_boto3, mock_get_details, mock_get_client):
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}, {"Name": "c1.xlarge"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "0.004"},
                                {"DimensionKey": "a1.xlarge", "Price": "0.007"},
                                {"DimensionKey": "c1.xlarge", "Price": "0.078"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "24.528"},
                                {"DimensionKey": "a1.xlarge", "Price": "49.056"},
                                {"DimensionKey": "c1.xlarge", "Price": "100.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.return_value = {
        "EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]
    }

    ap = _driver.AmiProduct(product_id="testing")
    ap.update(config, False)
    mock_start_change_set = mock_get_client.return_value.start_change_set

    assert mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][4][
        "ChangeType"
    ] == "RestrictInstanceTypes" and mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][4][
        "DetailsDocument"
    ] == {
        "InstanceTypes": ["c1.xlarge"]
    }


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.changesets.models.boto3")
def test_offer_create_pricing(mock_boto3, mock_get_details, mock_get_client):
    mock_get_details.return_value = {"Dimensions": [{"Name": "t2.micro"}, {"Name": "t2.large"}]}
    pricing_config = """
t2.micro,0.012,100
t2.large,0.034,800
"""
    offer_creation = _driver.offer_create(
        product_id="temp",
        buyer_accounts=["buyer1", "buyer2"],
        available_for_days=5,
        valid_for_days=2,
        offer_name="test_offer",
        eula_url="",
        pricing=io.StringIO(pricing_config),
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][3]["DetailsDocument"]["Terms"][0]["RateCards"][
        0
    ]["RateCard"][0] == {"DimensionKey": "t2.micro", "Price": "0.012"}


@patch("awsmp._driver.get_client")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.changesets.models.boto3")
def test_offer_create_eula_document(mock_boto3, mock_get_details, mock_get_client):
    mock_get_details.return_value = {"Dimensions": [{"Name": "t2.micro"}, {"Name": "t2.large"}]}
    pricing_config = """
t2.micro,0.012,100
t2.large,0.034,800
"""
    offer_creation = _driver.offer_create(
        product_id="temp",
        buyer_accounts=["buyer1", "buyer2"],
        available_for_days=5,
        valid_for_days=2,
        offer_name="test_offer",
        eula_url="https://test",
        pricing=io.StringIO(pricing_config),
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][5]["DetailsDocument"]["Terms"][0]["Documents"][
        0
    ] == {"Type": "CustomEula", "Url": "https://test"}
