from unittest.mock import patch

import pytest
import yaml
from botocore.exceptions import ClientError
from pydantic import ValidationError

from awsmp import _driver
from awsmp.errors import (
    AccessDeniedException,
    MissingInstanceTypeError,
    ResourceNotFoundException,
    UnrecognizedClientException,
)


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
    mock_get_details.return_value = {
        "Dimensions": [{"Name": "c3.2xlarge"}, {"Name": "c3.4xlarge"}, {"Name": "c3.8xlarge"}]
    }
    with open("./tests/prices.csv") as prices:
        ap.update_instance_types(prices, "Hrs")
    assert mock_get_client.return_value.start_change_set.call_count == 1
    assert mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][1][
        "DetailsDocument"
    ] == {"InstanceTypes": ["c4.large"]}
    assert (
        mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][2]["DetailsDocument"][
            "Terms"
        ][0]["RateCards"][0]["RateCard"][-1]["DimensionKey"]
        == "c4.large"
        and mock_get_client.return_value.start_change_set.call_args_list[0].kwargs["ChangeSet"][2]["DetailsDocument"][
            "Terms"
        ][0]["RateCards"][0]["RateCard"][-1]["Price"]
        == "0.00"
    )


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
@patch("awsmp._driver.changesets.models.boto3")
def test_ami_product_update(mock_boto3, mock_get_client):
    with open("./tests/test_config.yaml", "r") as f:
        config = yaml.safe_load(f)

    mock_boto3.client.return_value.describe_regions.return_value = {
        "Regions": [
            {"Endpoint": "ec2.us-east-1.amazonaws.com", "RegionName": "us-east-1", "OptInStatus": "opted-in"},
            {"Endpoint": "ec2.us-east-2.amazonaws.com", "RegionName": "us-east-2", "OptInStatus": "opted-in"},
        ]
    }

    ap = _driver.AmiProduct(product_id="testing")
    ap.update(config)
    mock_start_change_set = mock_get_client.return_value.start_change_set

    assert (
        "https://test-logourl"
        == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][0]["DetailsDocument"]["LogoUrl"]
    )
    assert {"Regions": ["us-east-1", "us-east-2"]} == mock_start_change_set.call_args_list[0].kwargs["ChangeSet"][1][
        "DetailsDocument"
    ]
