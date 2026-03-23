#!/usr/bin/env python

import logging
from typing import Dict, List, TextIO

import click

from .. import _driver, models
from . import _load_configuration, cli

logger = logging.getLogger(__name__)


def _load_ib_config(config: TextIO, required_fields: List[List[str]]) -> Dict:
    """Load and return the ec2_image_builder section from config."""
    full_fields = [["ec2_image_builder"] + field for field in required_fields]
    return _load_configuration(config, full_fields)["ec2_image_builder"]


@cli.group("image-builder")
def image_builder():
    """
    Manage EC2 Image Builder component products
    """
    pass


@image_builder.command("create")
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_create(dry_run):
    """
    Create a new AMI product listing for Image Builder components.
    """
    response = _driver.AmiProduct.create(dry_run=dry_run)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("add-version")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_add_version(product_id: str, config: TextIO, dry_run: bool) -> None:
    """
    Create IB component(s) and submit AddDeliveryOptions.
    """
    configs = _load_configuration(config, [["ec2_image_builder"]])
    ib_product = models.IBProduct(**configs["ec2_image_builder"])
    product = _driver.IbProduct(product_id=product_id, dry_run=dry_run)
    response = product.add_version(ib_product)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("restrict-version")
@click.option("--product-id", required=True, prompt=True)
@click.option("--delivery-option-id", required=True, multiple=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_restrict_version(product_id: str, delivery_option_id: tuple, dry_run: bool) -> None:
    """
    Submit RestrictDeliveryOptions for given delivery option IDs.
    """
    product = _driver.IbProduct(product_id=product_id, dry_run=dry_run)
    response = product.restrict_version(list(delivery_option_id))
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("update-description")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_update_description(product_id, config, dry_run):
    """
    Update product description from ec2_image_builder config.
    """
    ib_config = _load_ib_config(config, [["description"]])
    response = _driver.AmiProduct(product_id=product_id, dry_run=dry_run).update_description(ib_config["description"])
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("update-region")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_update_region(product_id, config, dry_run):
    """
    Update product regions from ec2_image_builder config.
    """
    ib_config = _load_ib_config(config, [["region"]])
    response = _driver.AmiProduct(product_id=product_id, dry_run=dry_run).update_regions(ib_config["region"])
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("update-instance-type")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option(
    "--allow-price-change/--no-allow-price-change",
    required=True,
    default=False,
    is_flag=True,
    prompt="Is price update allowed? (y/N). Default is False.",
)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_update_instance_type(product_id: str, config: TextIO, allow_price_change: bool, dry_run: bool) -> None:
    """
    Update instance types and pricing from ec2_image_builder config.
    """
    ib_config = _load_ib_config(config, [["offer"]])
    product = _driver.AmiProduct(product_id=product_id, dry_run=dry_run)
    response = product.update_instance_types(ib_config["offer"], allow_price_change)
    if response:
        print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
        print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("update-legal-terms")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_update_legal_terms(product_id, config, dry_run):
    """
    Update legal terms from ec2_image_builder config.
    """
    ib_config = _load_ib_config(config, [["offer", "eula_document"]])
    eula_document = ib_config["offer"]["eula_document"][0]
    response = _driver.AmiProduct(product_id=product_id, dry_run=dry_run).update_legal_terms(eula_document)
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("update-support-terms")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_update_support_terms(product_id, config, dry_run):
    """
    Update support terms from ec2_image_builder config.
    """
    ib_config = _load_ib_config(config, [["offer", "refund_policy"]])
    response = _driver.AmiProduct(product_id=product_id, dry_run=dry_run).update_support_terms(
        ib_config["offer"]["refund_policy"]
    )
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("release")
@click.option("--product-id", required=True, prompt=True)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_release(product_id, dry_run):
    """
    Publish Image Builder product as Limited.
    """
    product = _driver.AmiProduct(product_id=product_id, dry_run=dry_run)
    response = product.release()
    print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
    print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')


@image_builder.command("update")
@click.option("--product-id", required=True, prompt=True)
@click.option("--config", type=click.File("r"), required=True, prompt=True)
@click.option(
    "--allow-price-change/--no-allow-price-change",
    required=True,
    default=False,
    is_flag=True,
    prompt="Is price update allowed? (y/N). Default is False.",
)
@click.option("--dry-run/--no-dry-run", is_flag=True)
def ib_update(product_id: str, config: TextIO, allow_price_change: bool, dry_run: bool) -> None:
    """
    Update product details (description, region, instance type and pricing) in a single call
    from ec2_image_builder config.
    """
    ib_config = _load_ib_config(config, [["description"], ["region"], ["offer"]])
    configs = {
        "product": {
            "description": ib_config["description"],
            "region": ib_config["region"],
        },
        "offer": ib_config["offer"],
    }
    product = _driver.AmiProduct(product_id=product_id, dry_run=dry_run)
    response = product.update(configs, allow_price_change)
    if response:
        print(f'ChangeSet created (ID: {response["ChangeSetId"]})')
        print(f'https://aws.amazon.com/marketplace/management/requests/{response["ChangeSetId"]}')
