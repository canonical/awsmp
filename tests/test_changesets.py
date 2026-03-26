from decimal import Decimal
from typing import Any, Dict, List, Union, cast
from unittest.mock import patch

import pytest
import yaml
from pydantic import HttpUrl, ValidationError

from awsmp import changesets, models, types


@pytest.mark.parametrize(
    "eula_document,expected",
    [
        ({"type": "StandardEula", "version": "2022-07-14"}, {"Type": "StandardEula", "Version": "2022-07-14"}),
        ({"type": "CustomEula", "url": "foobar"}, {"Type": "CustomEula", "Url": "foobar"}),
    ],
)
def test_changeset_update_legal_terms_eula_options(eula_document, expected):
    result = changesets._changeset_update_legal_terms(eula_document)
    details_document = cast(Dict[str, Any], result["DetailsDocument"])
    assert details_document["Terms"][0]["Documents"][0] == expected


@pytest.mark.parametrize(
    "eula_document, expected_msg",
    [
        ({"type": "StandardEula"}, "Specify version of StandardEula"),
        ({"type": "CustomEula", "version": "foobar"}, "can't pass version of standard document"),
    ],
)
def test_changeset_update_legal_terms_invalid_eula_options(eula_document, expected_msg):
    with pytest.raises(ValidationError) as e:
        changesets._changeset_update_legal_terms(eula_document)

    assert expected_msg in str(e.value)


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", "test"),
        ("./tests/local_config/test_config_3.yaml", "test_prod"),
        ("./tests/local_config/test_config_4.yaml", "test_prod_id"),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_title(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["ProductTitle"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", "test_long_description"),
        ("./tests/local_config/test_config_3.yaml", "test_long_description\n\nvery_long"),
        ("./tests/local_config/test_config_4.yaml", "test_long_description\nnew_line\nanother_new_line"),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_long_desc(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["LongDescription"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", "test_short_description"),
        ("./tests/local_config/test_config_3.yaml", "test_short_description\nshort_description"),
        (
            "./tests/local_config/test_config_4.yaml",
            "test_long_description and another short description and short description",
        ),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_short_desc(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["ShortDescription"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", "https://test-logourl"),
        ("./tests/local_config/test_config_3.yaml", "https://test-logourl.pdf"),
        ("./tests/local_config/test_config_4.yaml", "https://test-logourl.svg"),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_logourl(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["LogoUrl"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", ["test_highlight_1"]),
        ("./tests/local_config/test_config_3.yaml", ["test_highlight_1", "test_highlight_2"]),
        ("./tests/local_config/test_config_4.yaml", ["test_highlight_1", "test_highlight_2", "test_highlight_3"]),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_highlights(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["Highlights"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", ["test_keyword_1"]),
        ("./tests/local_config/test_config_3.yaml", ["test_keyword_1", "test_keyword_2"]),
        (
            "./tests/local_config/test_config_4.yaml",
            [
                "test_keyword_1",
                "test_keyword_2",
                "test_keyword_3",
                "test_keyword_4",
                "test_keyword_5",
                "test_keyword_6",
            ],
        ),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_search_keywords(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["SearchKeywords"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", ["Migration"]),
        ("./tests/local_config/test_config_3.yaml", ["Migration", "Testing"]),
        ("./tests/local_config/test_config_4.yaml", ["Migration", "Testing", "Blockchain"]),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_description_categories(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["Categories"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", [{"Text": "test-link", "Url": "https://test-url/"}]),
        (
            "./tests/local_config/test_config_3.yaml",
            [{"Text": "test-link", "Url": "https://test-url/"}, {"Text": "test-link2", "Url": "https://test-url2/"}],
        ),
        (
            "./tests/local_config/test_config_4.yaml",
            [
                {"Text": "test-link1", "Url": "https://test-url1/"},
                {"Text": "test-link2", "Url": "https://test-url2/"},
                {"Text": "test-link3", "Url": "https://test-url3/"},
            ],
        ),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_additional_resources(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["AdditionalResources"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", "test_support_description"),
        ("./tests/local_config/test_config_3.yaml", "test_support_description\n\nwith new lines"),
        ("./tests/local_config/test_config_4.yaml", "test_support_description\nwith multiple line\nlines"),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_support_desc(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["SupportDescription"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_desc",
    [
        ("./tests/test_config.yaml", []),
        ("./tests/local_config/test_config_3.yaml", ["https://test-video"]),
        ("./tests/local_config/test_config_4.yaml", []),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_optional_video_urls(mock_boto3, file_path, expected_desc):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert details_document["VideoUrls"] == expected_desc


@pytest.mark.parametrize(
    "file_path, expected_region",
    [
        ("./tests/test_config.yaml", ["us-east-1", "us-east-2"]),
        ("./tests/local_config/test_config_3.yaml", ["us-east-1"]),
        ("./tests/local_config/test_config_4.yaml", ["us-east-2"]),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_region(mock_boto3, file_path, expected_region):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[1]["DetailsDocument"])
    assert details_document["Regions"] == expected_region


@pytest.mark.parametrize(
    "file_path, expected_future_region",
    [
        ("./tests/test_config.yaml", ["All"]),
        ("./tests/local_config/test_config_3.yaml", ["None"]),
        ("./tests/local_config/test_config_4.yaml", ["All"]),
    ],
)
@patch("awsmp.models.boto3")
def test_get_ami_product_update_changeset_future_region(mock_boto3, file_path, expected_future_region):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }
    with open(file_path, "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_changesets(
        "test-id", config["product"]["description"], config["product"]["region"]
    )
    details_document = cast(Dict[str, Any], res[2]["DetailsDocument"])
    assert details_document["FutureRegionSupport"]["SupportedRegions"] == expected_future_region


@patch("awsmp.models.boto3")
def test_get_ami_product_update_non_valid_changeset(mock_boto3):
    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    with pytest.raises(ValidationError):
        changesets.get_ami_listing_update_changesets("test-id", {}, {})


def test_get_ami_listing_update_version_changesets():
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_version_changesets(
        "test-id", config["product"]["version"]
    )
    details_document = cast(Dict[str, Any], res[0]["DetailsDocument"])
    assert (
        details_document["Version"]["VersionTitle"] == "test_version_title"
        and details_document["DeliveryOptions"][0]["Details"]["AmiDeliveryOptionDetails"]["AmiSource"]["AmiId"]
        == "ami-test"
    )


def test_get_ami_listing_update_version_non_valid_changesets():
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)
    config["product"]["version"]["access_role_arn"] = "iam::test"

    with pytest.raises(ValidationError):
        changesets.get_ami_listing_update_version_changesets("test-id", config["product"]["version"])


def test_get_ami_listing_update_instance_type_changesets_add_new_instance_type():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": 123.44, "hourly": 0.12},
            {"name": "c4.large", "yearly": 78.56, "hourly": 0.55},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, ["c4.large"], []
    )
    details_document = [cast(Dict[str, Any], item["DetailsDocument"]) for item in res[:]]
    assert (
        details_document[-1]["InstanceTypes"] == ["c4.large"]
        and details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][1]
        == {"DimensionKey": "c4.large", "Price": "0.55"}
        and details_document[0]["Terms"][1]["RateCards"][0]["RateCard"][1]
        == {"DimensionKey": "c4.large", "Price": "78.56"}
    )


def test_get_ami_listing_update_instance_type_changesets_add_new_multiple_instance_types():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": 123.44, "hourly": 0.12},
            {"name": "c4.large", "yearly": 78.56, "hourly": 0.55},
            {"name": "c5.large", "yearly": 100.78, "hourly": 1.28},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, ["c4.large", "c5.large"], []
    )
    details_document = [cast(Dict[str, Any], item["DetailsDocument"]) for item in res[:]]
    assert (
        details_document[-1]["InstanceTypes"] == ["c4.large", "c5.large"]
        and details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][1]
        == {"DimensionKey": "c4.large", "Price": "0.55"}
        and details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][2]
        == {"DimensionKey": "c5.large", "Price": "1.28"}
    )


def test_get_ami_listing_update_instance_type_changesets_add_new_instance_type_with_monthly_subscription():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": None, "hourly": 0.12},
            {"name": "c4.large", "yearly": None, "hourly": 0.55},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
        "monthly_subscription_fee": 265.00,
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, ["c4.large"], []
    )
    details_document = [cast(Dict[str, Any], item["DetailsDocument"]) for item in res[:]]
    assert details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][1] == {
        "DimensionKey": "c4.large",
        "Price": "0.55",
    } and details_document[0]["Terms"][1] == {
        "Type": "RecurringPaymentTerm",
        "CurrencyCode": "USD",
        "BillingPeriod": "Monthly",
        "Price": "265.0",
    }


def test_get_ami_listing_update_instance_type_changesets_restrict_instance_type():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": 123.44, "hourly": 0.12},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, [], ["c4.large"]
    )
    details_document = [cast(Any, item["DetailsDocument"]) for item in res[:]]

    assert (
        details_document[1]["InstanceTypes"] == ["c4.large"]
        and details_document[2][0]["Key"] == "c4.large"
        and details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][0]
        == {"DimensionKey": "c3.xlarge", "Price": "0.12"}
    )


def test_get_ami_listing_update_instance_type_changesets_restrict_multiple_instance_types():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": 123.44, "hourly": 0.12},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, [], ["c4.large", "c5.large"]
    )
    details_document = [cast(Any, item["DetailsDocument"]) for item in res[:]]

    assert (
        details_document[1]["InstanceTypes"] == ["c4.large", "c5.large"]
        and details_document[2][0]["Key"] == "c4.large"
        and details_document[2][1]["Key"] == "c5.large"
        and details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][0]
        == {"DimensionKey": "c3.xlarge", "Price": "0.12"}
    )


def test_get_ami_listing_update_instance_type_changesets_restrict_and_add_instance_type():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": 123.44, "hourly": 0.12},
            {"name": "c4.large", "yearly": 78.56, "hourly": 0.55},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, ["c4.large"], ["c1.medium"]
    )
    details_document = [cast(Any, item["DetailsDocument"]) for item in res[:]]
    assert (
        details_document[0]["Terms"][0]["RateCards"][0]["RateCard"][1] == {"DimensionKey": "c4.large", "Price": "0.55"}
        and details_document[1][0]["Key"] == "c4.large"
        and details_document[2]["InstanceTypes"] == ["c4.large"]
        and details_document[3]["InstanceTypes"] == ["c1.medium"]
        and details_document[4][0]["Key"] == "c1.medium"
    )


def test_get_ami_listing_update_instance_type_changesets_no_restrict_and_add_instance_type():
    offer_config: Dict[str, Any] = {
        "instance_types": [
            {"name": "c3.xlarge", "yearly": 123.44, "hourly": 0.12},
            {"name": "c4.large", "yearly": 78.56, "hourly": 0.55},
        ],
        "eula_document": [{"type": "StandardEula", "version": "2025-05-05"}],
        "refund_policy": "refund_policy",
    }
    offer_detail = models.Offer(**offer_config)
    res: List[types.ChangeSetType] = changesets.get_ami_listing_update_instance_type_changesets(
        "test-id", "test-offer_id", offer_detail, [], []
    )
    assert (
        res[0]["ChangeType"] == "UpdatePricingTerms"
        and res[0]["DetailsDocument"]["Terms"][0]["RateCards"][0]["RateCard"][0]["Price"] == "0.12"  # type: ignore
    )


# ---------------------------------------------------------------------------
# EC2 Image Builder changeset tests
# ---------------------------------------------------------------------------


class TestIBChangesets:
    def _build_ib_version(self):
        return models.IBVersion(
            version_title="1.0.0",
            release_notes="Initial release",
            access_role_arn="arn:aws:iam::123456789012:role/Test",
            delivery_options=[
                models.IBDeliveryOption(
                    title="Install",
                    usage_instructions="Add to pipeline",
                    component=models.IBComponent(
                        name="my-comp",
                        semantic_version="1.0.0",
                        platform="Linux",
                        document="schemaVersion: 1.0\n",
                    ),
                ),
            ],
        )

    def _build_ib_product(self):
        return models.IBProduct(
            description=models.Description(
                product_title="My Component",
                short_description="Short",
                long_description="Long",
                logourl=HttpUrl("https://example.com/logo"),
                highlights=["Feature 1"],
                categories=["Operating Systems"],
                search_keywords=["component"],
                support_description="Support info",
            ),
            region=models.Region(
                commercial_regions=["us-east-1"],
                future_region_support=True,
            ),
            offer=models.Offer(
                instance_types=[
                    models.InstanceTypePricing(
                        name="m5.large", price_hourly=Decimal("0.05"), price_annual=Decimal("400.00")
                    ),
                ],
                eula_document=[models.EulaDocumentItem(type="StandardEula", version="2022-07-14")],
                refund_policy="No refunds",
                monthly_subscription_fee=None,
            ),
            version=self._build_ib_version(),
        )

    @patch("awsmp.models.boto3")
    def test_add_ib_delivery_options_changeset(self, mock_boto3):
        mock_boto3.client.return_value.describe_regions.return_value = {
            "Regions": [
                {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            ]
        }
        ib_version = self._build_ib_version()
        arns = ["arn:aws:imagebuilder:us-east-1:123456789012:component/my-comp/1.0.0/1"]
        result = changesets._changeset_add_ib_delivery_options("prod-123", ib_version, arns)

        assert result["ChangeType"] == "AddDeliveryOptions"
        assert result["Entity"]["Identifier"] == "prod-123"
        delivery_opts = cast(Dict[str, Any], result["DetailsDocument"])["DeliveryOptions"]
        assert len(delivery_opts) == 1
        details = delivery_opts[0]["Details"]["Ec2ImageBuilderComponentDeliveryOptionDetails"]
        assert details["ComponentArn"] == arns[0]
        assert details["AccessRoleArn"] == "arn:aws:iam::123456789012:role/Test"

    def test_restrict_ib_delivery_options_changeset(self):
        result = changesets._changeset_restrict_ib_delivery_options("prod-123", ["do-aaa", "do-bbb"])
        assert result["ChangeType"] == "RestrictDeliveryOptions"
        details = cast(Dict[str, Any], result["DetailsDocument"])
        assert details["DeliveryOptionIds"] == ["do-aaa", "do-bbb"]

    @patch("awsmp.models.boto3")
    def test_get_ib_listing_add_version_changesets(self, mock_boto3):
        mock_boto3.client.return_value.describe_regions.return_value = {
            "Regions": [
                {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            ]
        }
        ib_product = self._build_ib_product()
        arns = ["arn:aws:imagebuilder:us-east-1:123456789012:component/my-comp/1.0.0/1"]
        result = changesets.get_ib_listing_add_version_changesets("prod-123", ib_product, arns)
        assert len(result) == 1
        assert result[0]["ChangeType"] == "AddDeliveryOptions"

    def test_get_ib_listing_restrict_version_changesets(self):
        result = changesets.get_ib_listing_restrict_version_changesets("prod-123", ["do-aaa"])
        assert len(result) == 1
        assert result[0]["ChangeType"] == "RestrictDeliveryOptions"
