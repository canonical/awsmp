*****
awsmp
*****

`awsmp` is a module and CLI tool to interact with the
AWS Marketplace API.

CLI usage
#########

The command line interface called `awsmp` accepts the standard
AWS environment variables (e.g. `AWS_PROFILE`). Note that Marketplace
interaction needs to happen in the `us-east-1` region (which is set
as the default in the CLI).

*`awsmpcli` is the legacy binary name, and still available outside of
snap builds*

Some examples how to use the CLI.


listing and showing available offers
************************************

Available offers can be listed:

.. code-block::

   $ awsmp entity-list Offer
   +---------------------------+------+------------+----------------------+
   |         entity-id         | name | visibility |     last-changed     |
   +---------------------------+------+------------+----------------------+
   | a8t4vhju1o9ibx6hfi9bnuo2x |  ''  |   Public   | 2021-09-03T08:14:37Z |
   +---------------------------+------+------------+----------------------+

Details about an available offer can be shown using the `enitity-id`:

.. code-block::

   $ awsmp entity-show a8t4vhju1o9ibx6hfi9bnuo2x
   {'AgreementToken': 'dummy-agreement-token',
    'Description': 'Worldwide offer for JUST FOR TESTING',
    'Id': 'a8t4vhju1o9ibx6hfi9bnuo2x',
    'MarkupPercentage': None,
    'Name': None,
    ... output stripped here ...


creating a new private offer
****************************

A new private offer can be created with:

.. code-block::

   $ awsmp private-offer create \
       --product-id 3a628887-30de-4d23-a949-93b32e4e4c5f \
       --buyer-accounts 887450378614 \
       --offer-name "toabctl testing" \
       --pricing prices.csv

   ChangeSet created (ID: 1mlxbdpmabfauymeeo12hg599)
   https://aws.amazon.com/marketplace/management/requests/1mlxbdpmabfauymeeo12hg599


Now a new request is available in the AWS Marketplace web UI.
That new request need to be in the state `Succeeded` before a buyer can see the offer.

The file `prices.csv` needs to be available and that file needs to contain all the
instance types (dimensions) available in the product.

generating a prices.csv file
****************************

The `awsmp private-offer create` command requires a `prices.csv` file be available.
That file contains 3 colums where the first column is the instance type, the
second column is the hourly price (in USD) and the third column is the annual price.

This file can be generated from an available offer, then adjusted and used to generate
a new offer. To generate the file for an available offer, do:

.. code-block::

   awsmp pricing-template \
       --offer-id offer-rsf4l7ilje2ze \
       --pricing prices.csv

This creates a `prices.csv` file for the offer with the entity Id `offer-rsf4l7ilje2ze`.


creating a new public AMI product
*********************************

A new public AMI product listing can be created following steps below:

1. Create product Id
.. code-block::
   awsmp public-offer create

   ChangeSet created (ID: gxy13m673kmhr4vdtpu0ltwf)
   https://aws.amazon.com/marketplace/management/requests/gxy13m673kmhr4vdtpu0ltwf

This request will generate offer id associated with product id. Offer id is required
to update instance type, legal term, release listing.

2. Add/Edit product description

Once product id is created, you can add/edit product description. Description fields can be found
below or please see the sample config file (listing_configuration.yaml)

.. code-block::

   description:
      product_title: str
      logourl: str
      video_urls: Optional[List[str]], can only have 1 url
      short_description: str
      long_description: str
      highlights: List[str]
      search_keywords: List[str]
      categories: List[str]
      support_description: str # Don't include space character at the beginning/end
      support_resources: str
      additional_resources: Optional[List[Dict[str, str]]]
      sku: Optional[str]

For empty value, please use '~' for str type and '[]' for List type

.. code-block::
   awsmp public-offer update-description \
      --product-id prod-xwpv7txqxg55e
      --config listing_configuration.yaml

If field value does not match with file format, it will show error before updating listing


3. Update/Add instance type
   3.1 Generate instance type file (.csv) and provide as input file when updating listing.

      *example instance_type.csv*

      .. code-block::
         m7a.8xlarge,0.00,0.00
         m7a.large,0.00,0.00
         m7a.medium,0.00,0.00
         m7a.xlarge,0.00,0.00
         m7i-flex.8xlarge,0.00,0.00
         m7i-flex.large,0.00,0.00
         m7i-flex.xlarge,0.00,0.00

      There are 2 cases you can generate instance type file.

      a. Using public-offer command
         If you create new listing and see what's available with given architecture and virtual type,
         call `awsmp public-offer instance-type-template` and file `instance_type.csv` will be created.
         You can remove or add instance types you want to update in the listing.

         .. code-block::
            awsmp public-offer instance-type-template \
               --arch x86_64 \
               --virt hvm

      b. Update pricing/add new available instance types
         To update/copying existing listing instance types or adding available instance types, we need all instance type information
         from the listing. (Please see below to find offer Id which is associated public product listing at the end of section)

         .. code-block::
            awsmp pricing-template \
               --offer-id offer-rsf4l7ilje2ze \
               --pricing prices.csv \
               --free

         You can append additional instance type at the end of this file or edit pricing (hourly which is second column) information.

   3.2 Once you have instance_type csv file, update listing with command below.

      a. Free listing update
         .. code-block::
            awsmp public-offer update-instnace-type \
               --product-id prod-xwpv7txqxg55e \
               --offer-id offer-t4vib6xp7tb3c \
               --instance-type-file instance_type.csv \
               --dimension-unit Hrs \
               --free Y
      
      b. Paid listing update
         .. code-block::
            awsmp public-offer update-instnace-type \
               --product-id prod-xwpv7txqxg55e \
               --offer-id offer-t4vib6xp7tb3c \
               --instance-type-file instance_type.csv \
               --dimension-unit Hrs \
               --free N

      `dimension-unit` is unit type of billing of this product. For free listing, please put Hrs.
      There are different types but currently available types are Hrs, Units.

      Offer Id is needed to update pricing terms for public offer. You can find this offer id from `Create product id`
      request in Step 1. Or login AWS console, go `AWS Marketplace` > `Manage subscriptions` and click the listing to find
      Offer Id under Agreements.

4. Update/Add region

Add and update region information to AMI product listing.

*example listing_configuration.yaml*

.. code-block::
   ...
   region:
      commercial_regions: List[str]
      future_region_support_region: bool
   ...

.. code-block::
   awsmp public-offer update-region \
      --product-id prod-xwpv7txqxg55e \
      --config listing_configuration.yaml

Gov region can't be enabled with API. Contact marketplace representative for gov region enablement

5. Add new version

Add new Ami version Ami to listing. Sample version config can be references in listing_configuration.yaml

.. code-block::
   ...
   version:
      version_title: str
      release_notes: str
      ami_id: str # Format should be starting with `ami-`
      access_role_arn: str # Format should be starting with 'arn:aws:iam::'
      os_user_name: str
      os_system_version: str
      os_system_name: str # This will be converted to Uppercase
      scanning_port: int # 1-65535
      usage_instructions: str
      recommended_instance_type: str # Please select among instance types you added in Step 2
      ip_protocol: Literal['tcp', 'udp']
      ip_ranges: List[str] # Upto 5 ranges can be added
      from_port: int # 1-65535
      to_port: int # 1-65535
   ...

.. code-block::
   awsmp public-offer update-version \
      --product-id prod-xwpv7txqxg55e
      --config listing_configuration.yaml

6. Update legal/support Terms

Legal/Support terms update in AMI product listing requires public offer id when you created in Step 1.

*example listing_configuration.yaml*
.. code-block::
   ...
   eula_url: "https://eula-example"
   refund_policy: |
      Absolutely no refund!
   ...

`refund_policy` is free form of text.

.. code-block::
   awsmp public-offer update-legal-terms \
      --offer-id offer-t4vib6xp7tb3c
      --config listing_configuration.yaml

.. code-block::
   awsmp public-offer update-support-terms \
      --offer-id offer-t4vib6xp7tb3c
      --config listing_configuration.yaml

7. Release AMI product listing

To release (published as limited), product id and public offer id are required.

.. code-block::
   awsmp public-offer release \
      --product-id prod-fwu3xsqup23cs
      --offer-id offer-t4vib6xp7tb3c
