#!/usr/bin/env python

import csv
import json
import logging
import time
from typing import Dict, List, Optional, TextIO

import click
import json_log_formatter  # type: ignore
import prettytable
import yaml
from botocore.exceptions import ClientError

from . import _driver, models, yaml_utils
from .errors import (
    AccessDeniedException,
    NoProductIdProvidedException,
    YamlMissingKeyException,
)

logger = logging.getLogger(__name__)


@click.group()
@click.option("--log-console/--no-log-console", default=False, is_flag=True, help="Do not log to console")
@click.option("--log-file", required=False, help="File to log to", type=click.Path(dir_okay=False))
@click.option("--debug", default=False, is_flag=True, help="Enable debug logging")
def cli(log_file, log_console, debug):

    log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logger.setLevel(log_level)

    if log_file:
        file_handler = logging.FileHandler(filename=log_file)
        file_handler.setFormatter(json_log_formatter.VerboseJSONFormatter())
        logger.addHandler(file_handler)
    if log_console:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


@cli.group("private-offer")
def private_offer():
    """
    Create and update private offers
    """
    pass


@cli.group("public-offer")
def public_offer():
    """
    Create and update public offers (Free, 3p)
    """
    pass


@cli.group("inspect")
def inspect():
    """
    Inspect marketplace offers
    """
    pass


@inspect.command("entity-list")
@click.argument("entity-type", type=click.Choice(["Offer", "AmiProduct"]))
@click.option("--filter-visibility", multiple=True, type=click.Choice(["Public", "Restricted", "Limited"]))
def entity_list(entity_type, filter_visibility):
    """
    List available entities. Currently supported are entities of type "Offer"
    and "AmiProduct".
    """
    entity_list = _driver.list_entities(entity_type)
    t = prettytable.PrettyTable()
    t.field_names = ["entity-id", "name", "visibility", "last-changed"]
    for _, entity in entity_list.items():
        if not filter_visibility or entity["Visibility"] in filter_visibility:
            t.add_row([entity["EntityId"], entity["Name"], entity["Visibility"], entity["LastModifiedDate"]])
    print(t.get_string(sortby="last-changed"))


@inspect.command("entity-show", help="Show a specific entity")
@click.argument("entity-id")
def entity_show(entity_id):
    details = _driver.get_entity_details(entity_id)
    print(json.dumps(details, indent=2))


@inspect.command("entity-versions-count")
def entity_versions_count():
    """
    List each marketplace entry with it's number of versions, sorted by number of versions
    """
    entity_dict = _driver.list_entities("AmiProduct")
    versions = [
        (entity_id, len(_driver.get_entity_versions(entity_id)), entity_dict[entity_id]["Name"])
        for entity_id in entity_dict.keys()
    ]

    for version in sorted(versions, key=lambda x: x[1]):
        print(f"{version[0]} - {version[1]} - {version[2]}")


@inspect.command("entity-versions-list")
@click.argument("entity-id")
def entity_versions_list(entity_id):
    """
    List all versions for a provided entity id.
    """
    versions = _driver.get_entity_versions(entity_id)
    t = prettytable.PrettyTable()
    t.field_names = ["CreationDate", "Id", "version title"]
    for v in versions:
        t.add_row([v["CreationDate"], v["Id"], v["VersionTitle"]])
    print(t.get_string(sortby="CreationDate"))


@inspect.command("entity-diff")
@click.argument("entity-id")
@click.argument("config", type=click.File("r"), required=True)
def entity_get_diff(entity_id: str, config: TextIO):
    """
    Get the differences between marketplace listing and local configuration file.

    :param str entity_id: Product Id of a marketplace listing
    :param TextIO config: Path of local configuration file
    :return None
    :rtype None
    """

    entity_from_listing = models.EntityModel(**_driver.get_full_response(entity_id))
    logger.info(entity_from_listing)
    logger.debug(entity_from_listing)
    with open(config.name, "r") as f:
        yaml_config = yaml.safe_load(f)
    local_config_entity = models.EntityModel.get_entity_from_yaml(yaml_config)

    diff = entity_from_listing.get_diff(local_config_entity)

    print(repr(diff))


@private_offer.command("create")
@click.option("--product-id", required=True, prompt=True)
@click.option("--buyer-accounts", multiple=True)
@click.option("--available-for-days", required=True, default=14, type=int, prompt=True)
@click.option("--valid-for-days", required=True, default=1095, type=int, prompt=True)
@click.option("--with-support", is_flag=True, default=False, prompt=True)
@click.option("--customer-name", type=str, required=True, prompt=True)
@click.option(
    "--eula-url",
    type=str,
    required=False,
    prompt="EULA Url (Will default to the standard AWS EULA if left blank)",
    default="",
    envvar="AWSMP_EULA_URL",
)
@click.option("--pricing", type=click.File("r"), required=True, prompt=True)
def offer_create(
    product_id,
    buyer_accounts,
    available_for_days,
    valid_for_days,
    with_support,
    customer_name,
    eula_url,
    pricing,
):
    """
    Create a new private offer.

    The file name passed via --pricing **must** be a .csv file without headers
    and 3 columns. The 1st column is the instance type name, 2nd column is the hourly price
    and the 3rd column is the annual price. E.g.:

    m6i.xlarge,0.007,49.056
    t2.nano,0.002,12.264
    r5d.24xlarge,0.168,1177.344

    Note: **all** instance types available in the product (referenced by --product-id)
    must be listed in this .csv file.

    The --available-for-days parameter says how long the offer can be accepted.
    The --valid-for-days parameter says how long the offer is valid when it was accepted
    The --eula-url option can be left blank if the default aws EULA is acceptable.
        The value can also be set via the `AWSMP_EULA_URL` environment variable
    """
    if not buyer_accounts:
        buyers = click.prompt("Please enter all buyer accounts separated by a comma")
        buyer_accounts = [b.strip() for b in buyers.split(",")]

    offer_name = _driver.create_offer_name(product_id, buyer_accounts, with_support, customer_name)

    click.echo(f"> {offer_name}")
    confirm = click.confirm("Is the offer name listed above correct?")
    if not confirm:
        offer_name = click.prompt("Please enter the offer name in full")

    response = _driver.offer_create(
        product_id, buyer_accounts, available_for_days, valid_for_days, offer_name, eula_url, pricing
    )

    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@cli.command("pricing-template", help="Generate pricing template for public/private offers")
@click.option("--offer-id", required=True)
@click.option("--pricing", type=click.File("w+"), required=True)
@click.option("--free/--no-free", default=False)
def offer_pricing_template(offer_id, pricing, free):
    """
    Create a pricing template (.csv file) based on a given offer
    """
    client = _driver.get_client()
    e = client.describe_entity(Catalog="AWSMarketplace", EntityId=offer_id)
    details = e["DetailsDocument"]

    prices_hourly = {}
    prices_annual = {}
    for term in details["Terms"]:
        if term["Type"] not in ["UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"]:
            continue
        for rate_card in term["RateCards"]:
            for d in rate_card["RateCard"]:
                if term["Type"] == "UsageBasedPricingTerm":
                    # hourly
                    prices_hourly[d["DimensionKey"]] = d["Price"]
                elif term["Type"] == "ConfigurableUpfrontPricingTerm":
                    # annual
                    prices_annual[d["DimensionKey"]] = d["Price"]
                else:
                    raise Exception(f'Unknown terms type {term["type"]}')

    # both should have the same keys so calculate the symmetric difference
    # this should never happen given that we get the data from an available offer
    # free listing can be skipped since it doesn't have annual pricing
    if not free:
        if prices_hourly.keys() ^ prices_annual.keys():
            raise Exception("instance type dimensions are not identical in hourly and annual prices")
    else:
        prices_annual = prices_hourly

    csvwriter = csv.writer(pricing)
    for instance_type in sorted(prices_hourly.keys()):
        csvwriter.writerow([instance_type, prices_hourly[instance_type], prices_annual[instance_type]])


@public_offer.command("create")
def ami_product_create():
    """
    Create a new AMI product listing
    """
    response = _driver.AmiProduct.create()

    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("update-description")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
def ami_product_update_description(product_id, config):
    """
    Update AMI product description
    """
    # Load yaml file
    desc = _load_configuration(config, [["product", "description"]])["product"]["description"]
    response = _driver.AmiProduct(product_id=product_id).update_description(desc)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("update-instance-type")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option(
    "--allow-price-change/--no-allow-price-change",
    required=True,
    default=False,
    type=click.BOOL,
    is_flag=True,
    prompt="Is price update allowed? (y). Default is False.",
)
def ami_product_update_instance_type(product_id: str, config: TextIO, allow_price_change: bool) -> None:
    """
    Update AMI product instance type
    :param str product_id: Id of listing
    :param TextIO config: file path of local configuration file
    :param bool allow_price_change: flag of allowing pricing change to update instance type information
    :return: None
    :rtype: None
    """
    product = _driver.AmiProduct(product_id=product_id)
    offer_config = _load_configuration(config, [["offer"]])["offer"]
    response = product.update_instance_types(offer_config, allow_price_change)
    if response:
        print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
        print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("instance-type-template")
@click.option("--arch", required=True, prompt=True, type=click.Choice(["x86_64", "arm64", "i386"]))
@click.option("--virt", required=True, prompt=True, type=click.Choice(["hvm", "paravirtual"]))
def ami_product_instance_type_template(arch, virt):
    """
    Generate AMI product instance type template
    """
    # Load yaml file
    client = _driver.get_client(service_name="ec2")
    try:
        e = client.get_instance_types_from_instance_requirements(
            ArchitectureTypes=[arch],
            VirtualizationTypes=[virt],
            InstanceRequirements={
                "VCpuCount": {
                    "Min": 0,
                },
                "MemoryMiB": {
                    "Min": 0,
                },
            },
        )
    except ClientError:
        logger.exception("Profile does not have EC2 service access. Check your profile role or services.")
        raise AccessDeniedException(service_name="ec2")

    available_instances = [i["InstanceType"] for i in e["InstanceTypes"]]
    with open("instance_type.csv", "w") as f:
        csvwriter = csv.writer(f)
        for instance in available_instances:
            csvwriter.writerow([instance, 0.00, 0.00])
    print(f"Available instance types are exported in instance_type.csv file.")


@public_offer.command("update-region")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
def ami_product_update_regions(product_id, config):
    """
    Update AMI product region
    """
    # Load yaml file
    region_config = _load_configuration(config, [["product", "region"]])["product"]["region"]

    product = _driver.AmiProduct(product_id=product_id)
    response = product.update_regions(region_config)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("update-version")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
def ami_product_update_version(product_id, config):
    """
    Update AMI product version
    """
    # Load yaml file
    version_config = _load_configuration(config, [["product", "version"]])["product"]["version"]

    product = _driver.AmiProduct(product_id=product_id)
    response = product.update_version(version_config)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("update-legal-terms")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
def ami_product_update_legal_terms(product_id, config):
    """
    Update AMI product legal terms
    """
    # Load yaml file
    eula_url = _load_configuration(config, [["offer", "eula_document"]])["offer"]["eula_document"][0]

    product = _driver.AmiProduct(product_id=product_id)
    response = product.update_legal_terms(eula_url)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("update-support-terms")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
def ami_product_update_support_terms(product_id, config):
    """
    Update AMI product support terms
    """
    # Load yaml file
    refund_policy = _load_configuration(config, [["offer", "refund_policy"]])["offer"]["refund_policy"]

    product = _driver.AmiProduct(product_id=product_id)
    response = product.update_support_terms(refund_policy)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("release")
@click.option("--product-id", required=True, prompt=True)
def ami_product_release(product_id):
    """
    Publish AMI product as Limited
    """

    product = _driver.AmiProduct(product_id=product_id)
    response = product.release()
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("update")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option(
    "--allow-price-change/--no-allow-price-change",
    required=True,
    default=False,
    is_flag=True,
    prompt="Is price update allowed? (y/N). Default is False.",
)
def ami_product_update(product_id: str, config: TextIO, allow_price_change: bool) -> None:
    """
    Update AMI product details (description, region, instnance type and pricing) in a single call
    :param str product_id: Id of listing
    :param TextIO config: file path of local configuration file
    :param bool allow_price_change: flag of allowing pricing change to update instance type information
    :return: None
    :rtype: None
    """

    # Load yaml file
    configs = _load_configuration(config, [["product", "description"], ["product", "region"], ["offer"]])
    product = _driver.AmiProduct(product_id=product_id)
    response = product.update(configs, allow_price_change)

    if response:
        print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
        print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@public_offer.command("download")
@click.option("--product-id", required=True, prompt=True, help="Product id of the listing")
@click.option(
    "--config", type=click.File("w+"), required=True, prompt=True, help="File path of local configuration file"
)
def ami_product_download(product_id: str, config: TextIO) -> None:
    """
    Download YAML local configuration from AWS Marketplace live listing.
    :param str product_id: Id of listing
    :param TextIO config: file path of local configuration file to download
    :return: None
    :rtype: None
    """

    yaml_config = models.EntityModel(**_driver.get_full_response(product_id)).to_dict()
    yaml_utils.dump(yaml_config, config)
    print(f"{config.name} has been successfully written")


def _load_configuration(config_path: TextIO, required_fields: List[List[str]]) -> Dict:
    """
    Check if keys exist in config file before creating changeset and return config dict

    :param TextIO config_path: File path for configuration yaml file
    :param: List of :str: required_fields: List of required keys to request (e.g. [["product", "description"]] or [["product"]])
    :return: dictionary of configuration
    :rtype: Dict
    """

    with open(config_path.name, "r") as f:
        config = yaml.safe_load(f)
        list_of_missing_keys: List[List[str]] = []

    for keys in required_fields:
        missing_keys = []
        temp_config = config
        for key in keys:
            if key not in temp_config:
                idx = keys.index(key)
                missing_keys = keys[idx:]

                break
            else:
                if isinstance(temp_config[key], dict):
                    temp_config = temp_config[key]
        if missing_keys:
            list_of_missing_keys.append(missing_keys)
    if list_of_missing_keys:
        logger.exception(f"Configuration file is missing: {missing_keys}" for missing_keys in list_of_missing_keys)
        raise YamlMissingKeyException(missing_keys=list_of_missing_keys)
    return config
