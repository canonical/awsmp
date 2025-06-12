import json
import tempfile
from io import StringIO
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from awsmp import _driver, changesets, cli, errors, models


@patch("awsmp._driver.get_client")
def test_offer_pricing_template(mock_get_client):
    mock_get_client.return_value.describe_entity.return_value = {
        "DetailsDocument": {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "Id": "usage_id",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "m6i.xlarge", "Price": "0.007"},
                                {"DimensionKey": "t2.nano", "Price": "0.002"},
                                {"DimensionKey": "r5d.24xlarge", "Price": "0.168"},
                            ]
                        }
                    ],
                },
                {
                    "Type": "ConfigurableUpfrontPricingTerm",
                    "Id": "annual_id",
                    "CurrencyCode": "USD",
                    "RateCards": [
                        {
                            "Selector": {"Type": "Duration", "Value": "P365D"},
                            "Constraints": {
                                "MultipleDimensionSelection": "Allowed",
                                "QuantityConfiguration": "Allowed",
                            },
                            "RateCard": [
                                {"DimensionKey": "m6i.xlarge", "Price": "49.056"},
                                {"DimensionKey": "t2.nano", "Price": "12.264"},
                                {"DimensionKey": "r5d.24xlarge", "Price": "1177.344"},
                            ],
                        }
                    ],
                },
            ]
        }
    }
    runner = CliRunner()
    pricing_file = tempfile.NamedTemporaryFile()
    runner.invoke(cli.offer_pricing_template, ["--offer-id", "some-offer-id", "--pricing", pricing_file.name])

    results = []
    with open(pricing_file.name, "r") as fh:
        results = [l.strip() for l in fh.readlines()]
    assert results == ["m6i.xlarge,0.007,49.056", "r5d.24xlarge,0.168,1177.344", "t2.nano,0.002,12.264"]


@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_offer_create(mock_get_client, mock_get_entity_details):
    mock_get_entity_details.return_value = {"Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}]}
    with open("./tests/prices.csv") as prices:
        _driver.offer_create(
            "some-product-id",
            [
                "123",
            ],
            10,
            365,
            "Some offer name",
            "",
            prices,
        )
    mock_start_change_set = mock_get_client.return_value.start_change_set

    assert {
        "RateCard": [{"DimensionKey": "c3.2xlarge", "Price": "0.014"}, {"DimensionKey": "c3.4xlarge", "Price": "0.028"}]
    } == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][3]["DetailsDocument"]["Terms"][0]["RateCards"][0]


def test_ami_product_instance_type_template():
    """
    Test with invalid architecture argument
    """
    runner = CliRunner()
    result = runner.invoke(cli.ami_product_instance_type_template, ["--arch", "invalid", "--virt", "hvm"])
    # click exceptions get translated to SystemEixt unless specified
    assert isinstance(result.exception, SystemExit)


@pytest.mark.parametrize(
    "missing_key, expected_exception, expected_message",
    [
        (
            [["product", "test_description"]],
            errors.YamlMissingKeyException,
            "does not have the following missing keys:\ntest_description",
        ),
        (
            [["offer", "test_eula"]],
            errors.YamlMissingKeyException,
            "does not have the following missing keys:\noffer->test_eula",
        ),
    ],
)
def test_missing_keys_in_configuration(missing_key, expected_exception, expected_message):
    """
    Test with missing keys in configuration.yaml file
    """
    mock_path = MagicMock()
    mock_path.name = "./tests/description.yaml"
    with pytest.raises(expected_exception) as e:
        cli._load_configuration(mock_path, missing_key)
    assert expected_message in str(e.value)


@patch("awsmp._driver.get_public_offer_id")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp.models.boto3")
def test_entity_get_diff_no_diff(mock_boto3, mock_get_entity_details, mock_get_public_offer_id):
    """
    Test get_diff call
    """
    with open("./tests/test_config.json") as f:
        mock_prod_resp = json.load(f)
        mock_prod_resp.pop("Terms")
        mock_prod_resp["Versions"] = [mock_prod_resp["Versions"]]

    with open("./tests/test_config.json") as f:
        mock_offer_resp = {"Terms": json.load(f)["Terms"]}

    mock_get_public_offer_id.return_value = "test-offer-id"
    mock_get_entity_details.side_effect = [mock_prod_resp, mock_offer_resp]

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    local_config_file = "./tests/local_config/test_config_1.yaml"
    expected_diff: dict[str, List[Any]] = {"added": [], "removed": [], "changed": []}

    runner = CliRunner()
    result = runner.invoke(cli.entity_get_diff, ["temp-list", local_config_file])
    assert result.output.strip() == json.dumps(expected_diff, indent=2).strip()


@patch("awsmp._driver.get_public_offer_id")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp.models.boto3")
def test_entity_get_diff(mock_boto3, mock_get_entity_details, mock_get_public_offer_id):
    with open("./tests/test_config.json") as f:
        mock_prod_resp = json.load(f)
        mock_prod_resp.pop("Terms")
        mock_prod_resp["Versions"] = [mock_prod_resp["Versions"]]

    with open("./tests/test_config.json") as f:
        mock_offer_resp = {"Terms": json.load(f)["Terms"]}

    mock_get_public_offer_id.return_value = "test-offer-id"
    mock_get_entity_details.side_effect = [mock_prod_resp, mock_offer_resp]

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.eu-west-1.amazonaws.com", "RegionName": "eu-west-1", "OptInStatus": "opted-in"},
        ]
    }

    local_config_file = "./tests/local_config/test_config_2.yaml"
    expected_diff: dict[str, List[Any]] = {
        "added": [],
        "removed": [],
        "changed": [
            {
                "name": "Highlights",
                "old_value": ["test_highlight_1"],
                "new_value": ["test_highlight_1", "test_highlight_2"],
            },
            {
                "name": "Regions",
                "old_value": ["us-east-1", "us-east-2"],
                "new_value": ["us-east-1", "us-east-2", "eu-west-1"],
            },
        ],
    }

    runner = CliRunner()
    result = runner.invoke(cli.entity_get_diff, ["temp-list", local_config_file])

    assert result.output.strip() == json.dumps(expected_diff, indent=2).strip()


@patch("awsmp._driver.get_public_offer_id")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp.models.boto3")
def test_entity_get_diff_terms(mock_boto3, mock_get_entity_details, mock_get_public_offer_id):
    with open("./tests/test_config.json") as f:
        mock_prod_resp = json.load(f)
        mock_prod_resp.pop("Terms")
        mock_prod_resp["Versions"] = [mock_prod_resp["Versions"]]

    with open("./tests/test_config.json") as f:
        mock_offer_resp = {"Terms": json.load(f)["Terms"]}

    mock_get_public_offer_id.return_value = "test-offer-id"
    mock_get_entity_details.side_effect = [mock_prod_resp, mock_offer_resp]

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    local_config_file = "./tests/local_config/test_config_5.yaml"
    expected_diff: dict[str, List[Any]] = {
        "added": [],
        "removed": [],
        "changed": [
            {
                "name": "SupportTerm",
                "old_value": {"Type": "SupportTerm", "RefundPolicy": "test_refund_policy_term\n"},
                "new_value": {"Type": "SupportTerm", "RefundPolicy": "100% refund\n"},
            },
        ],
    }

    runner = CliRunner()
    result = runner.invoke(cli.entity_get_diff, ["temp-list", local_config_file])

    assert result.output.strip() == json.dumps(expected_diff, indent=2).strip()


@pytest.mark.parametrize(
    "config_name, expected_diff",
    [
        (
            "./tests/local_config/test_config_6.yaml",
            {
                "added": [],
                "removed": [],
                "changed": [
                    {
                        "name": "ConfigurableUpfrontPricingTerm",
                        "old_value": {"DimensionKey": "a1.large", "Price": "24.528"},
                        "new_value": {"DimensionKey": "a1.large", "Price": "30.0"},
                    },
                ],
            },
        ),
        (
            "./tests/local_config/test_config_7.yaml",
            {
                "added": [],
                "removed": [],
                "changed": [],
            },
        ),
    ],
)
@patch("awsmp._driver.get_public_offer_id")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp.models.boto3")
def test_entity_get_diff_pricing_terms(
    mock_boto3, mock_get_entity_details, mock_get_public_offer_id, config_name, expected_diff
):
    with open("./tests/test_config.json") as f:
        mock_prod_resp = json.load(f)
        mock_prod_resp.pop("Terms")
        mock_prod_resp["Versions"] = [mock_prod_resp["Versions"]]

    with open("./tests/test_config.json") as f:
        mock_offer_resp = {"Terms": json.load(f)["Terms"]}

    mock_get_public_offer_id.return_value = "test-offer-id"
    mock_get_entity_details.side_effect = [mock_prod_resp, mock_offer_resp]

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    runner = CliRunner()
    result = runner.invoke(cli.entity_get_diff, ["temp-list", config_name])
    assert result.output.strip() == json.dumps(expected_diff, indent=2).strip()


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_details(mock_get_client, mock_get_details, mock_boto3):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "0.004"},
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
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    runner.invoke(
        cli.ami_product_update,
        ["--product-id", "some-prod-id", "--config", "./tests/test_config.yaml"],
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert {"Regions": ["us-east-1", "us-east-2"]} == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][1][
        "DetailsDocument"
    ] and ["test_highlight_1"] == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"][
        "Highlights"
    ]


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_details_pricing_change(mock_get_client, mock_get_details, mock_boto3, caplog):
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
                                {"DimensionKey": "a1.xlarge", "Price": "50.056"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()

    with caplog.at_level("ERROR", logger="awsmp._driver"):
        runner.invoke(
            cli.ami_product_update,
            ["--product-id", "some-prod-id", "--config", "./tests/test_config.yaml", "--no-allow-price-change"],
        )

    assert any(
        "There are pricing changes in either hourly or annual prices." in record.message for record in caplog.records
    )


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_details_raise_exception(mock_get_client, mock_get_details, mock_boto3):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}]},
        {"Description": {"Visibility": "Restricted"}},
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

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()

    with pytest.raises(errors.AmiPriceChangeError) as excInfo:
        runner.invoke(
            cli.ami_product_update,
            ["--product-id", "some-prod-id", "--config", "./tests/test_config.yaml", "--no-allow-price-change"],
            catch_exceptions=False,
        )

    assert "Restricted listings may not have instance types updated." in excInfo.value.args[0]


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_details_restrict_instance_types(mock_get_client, mock_get_details, mock_boto3):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}, {"Name": "t1.micro"}]},
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
                                {"DimensionKey": "t1.micro", "Price": "0.008"},
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
                                {"DimensionKey": "t1.micro", "Price": "80.00"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()

    runner.invoke(
        cli.ami_product_update,
        ["--product-id", "some-prod-id", "--config", "./tests/test_config.yaml"],
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert (
        mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][4]["DetailsDocument"]
        == {"InstanceTypes": ["t1.micro"]}
        and mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][4]["ChangeType"] == "RestrictInstanceTypes"
    )


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_details_pricing_change_allowed(
    mock_get_client, mock_get_details, mock_boto3, caplog
):
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
                                {"DimensionKey": "a1.xlarge", "Price": "50.056"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    runner.invoke(
        cli.ami_product_update,
        [
            "--product-id",
            "some-prod-id",
            "--config",
            "./tests/test_config.yaml",
            "--allow-price-change",
        ],
    )

    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert (
        mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][3]["ChangeType"] == "UpdatePricingTerms"
        and mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][3]["DetailsDocument"]["Terms"][1]["RateCards"][
            0
        ]["RateCard"][1]["Price"]
        == "49.056"
    )


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_instance_type(mock_get_client, mock_get_details, mock_boto3):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}]},
        {"Description": {"Visibility": "Limited"}},
        {
            "Terms": [
                {
                    "Type": "UsageBasedPricingTerm",
                    "RateCards": [
                        {
                            "RateCard": [
                                {"DimensionKey": "a1.large", "Price": "0.004"},
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
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    runner.invoke(
        cli.ami_product_update_instance_type,
        [
            "--product-id",
            "some-prod-id",
            "--config",
            "./tests/test_config.yaml",
        ],
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert (
        mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]["Terms"][1]["RateCards"][0][
            "RateCard"
        ][1]["Price"]
        == "49.056"
    ) and mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][1]["DetailsDocument"][0]["Key"] == "a1.xlarge"


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_instance_type_restrict_instance_type(
    mock_get_client, mock_get_details, mock_boto3
):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}, {"Name": "t1.micro"}]},
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
                                {"DimensionKey": "t1.micro", "Price": "0.001"},
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
                                {"DimensionKey": "t1.micro", "Price": "0.4"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    runner.invoke(
        cli.ami_product_update_instance_type,
        [
            "--product-id",
            "some-prod-id",
            "--config",
            "./tests/test_config.yaml",
        ],
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert (
        mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]["Terms"][1]["RateCards"][0][
            "RateCard"
        ][1]["Price"]
        == "49.056"
    ) and mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][2]["DetailsDocument"][0]["Key"] == "t1.micro"


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_instance_type_pricing_change(mock_get_client, mock_get_details, mock_boto3):
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
                                {"DimensionKey": "a1.xlarge", "Price": "30.056"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    runner.invoke(
        cli.ami_product_update_instance_type,
        [
            "--product-id",
            "some-prod-id",
            "--config",
            "./tests/test_config.yaml",
            "--allow-price-change",
        ],
    )
    mock_start_change_set = mock_get_client.return_value.start_change_set
    assert (
        mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]["Terms"][1]["RateCards"][0][
            "RateCard"
        ][1]["Price"]
        == "49.056"
    )


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_instance_type_pricing_change_not_allowed(
    mock_get_client, mock_get_details, mock_boto3
):
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
                                {"DimensionKey": "a1.xlarge", "Price": "30.056"},
                            ]
                        }
                    ],
                },
            ]
        },
    ]

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    res = runner.invoke(
        cli.ami_product_update_instance_type,
        ["--product-id", "some-prod-id", "--config", "./tests/test_config.yaml"],
    )
    assert res.return_value == None


@patch("awsmp._driver.changesets.models.boto3")
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_client")
def test_public_offer_product_update_instance_type_pricing_change_exception(
    mock_get_client, mock_get_details, mock_boto3
):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    mock_get_details.side_effect = [
        {"Dimensions": [{"Name": "a1.large"}, {"Name": "a1.xlarge"}]},
        {"Description": {"Visibility": "Restricted"}},
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

    mock_get_client.return_value.list_entities.side_effect = [
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
        {"EntitySummaryList": [{"EntityType": "Offer", "EntityId": "test-offer"}]},
    ]

    runner = CliRunner()
    res = runner.invoke(
        cli.ami_product_update_instance_type,
        ["--product-id", "some-prod-id", "--config", "./tests/test_config.yaml", "--no-allow-price-change"],
    )
    assert res.exit_code == 1 and res.exc_info is not None and "Restricted listings" in res.exc_info[1].args[0]


@pytest.mark.parametrize(
    "key1, key2, value",
    [
        ("description", "product_title", "test"),
        ("description", "categories", ["Migration"]),
        ("description", "long_description", "test_long_description\n"),
        ("version", "version_title", "Test Ubuntu AMI"),
        ("version", "usage_instructions", "test_usage_instruction\n"),
        ("version", "ami_id", "ami-12345678910"),
        ("description", "support_description", "test_support_description\n"),
        ("region", "commercial_regions", ["us-east-1", "us-east-2"]),
        ("region", "gov_regions", ["us-gov-east-1", "us-gov-west-1"]),
        ("region", "future_region_support", True),
    ],
)
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_public_offer_id")
def test_public_offer_product_download_product(mock_get_public_offer_id, mock_get_entity_details, key1, key2, value):
    with open("./tests/test_config.json") as f:
        mock_prod_resp = json.load(f)
        mock_prod_resp.pop("Terms")

    mock_prod_resp["Versions"]["CreationDate"] = "2025-01-01"
    mock_prod_resp["Versions"] = [mock_prod_resp["Versions"]]
    mock_prod_resp["RegionAvailability"]["Regions"] += ["us-gov-east-1", "us-gov-west-1"]

    with open("./tests/test_config.json") as f:
        mock_offer_resp = {"Terms": json.load(f)["Terms"]}

    mock_get_entity_details.side_effect = [mock_prod_resp, mock_offer_resp]
    mock_get_public_offer_id.return_value = "test-offer-id"

    runner = CliRunner()
    config_file = tempfile.NamedTemporaryFile()
    res = runner.invoke(
        cli.ami_product_download,
        ["--product-id", "some-prod-id", "--config", config_file.name],
    )

    with open(config_file.name, "r") as f:
        config = yaml.safe_load(f)

    assert config["product"][key1][key2] == value


@pytest.mark.parametrize(
    "key1, key2, value",
    [
        ("offer", "refund_policy", "test_refund_policy_term\n"),
        (
            "offer",
            "instance_types",
            [
                {"name": "a1.large", "hourly": "0.004", "yearly": "24.528"},
                {"name": "a1.xlarge", "hourly": "0.007", "yearly": "49.056"},
            ],
        ),
        ("offer", "eula_document", [{"type": ""}]),
    ],
)
@patch("awsmp._driver.get_entity_details")
@patch("awsmp._driver.get_public_offer_id")
def test_public_offer_product_download_offer(mock_get_public_offer_id, mock_get_entity_details, key1, key2, value):
    with open("./tests/test_config.json") as f:
        mock_prod_resp = json.load(f)
        mock_prod_resp.pop("Terms")

    mock_prod_resp["Versions"]["CreationDate"] = "2025-01-01"
    mock_prod_resp["Versions"] = [mock_prod_resp["Versions"]]

    with open("./tests/test_config.json") as f:
        mock_offer_resp = {"Terms": json.load(f)["Terms"]}

    mock_get_entity_details.side_effect = [mock_prod_resp, mock_offer_resp]
    mock_get_public_offer_id.return_value = "test-offer-id"

    runner = CliRunner()
    config_file = tempfile.NamedTemporaryFile()
    res = runner.invoke(
        cli.ami_product_download,
        ["--product-id", "some-prod-id", "--config", config_file.name],
    )

    with open(config_file.name, "r") as f:
        config = yaml.safe_load(f)

    assert config[key1][key2] == value
