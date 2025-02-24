How to create a public offer
============================

To create a new public AMI product listing in the `AWS marketplace management portal`_, use the API calls described below:


Create product ID
-----------------

.. code-block:: sh

   awsmp public-offer create

   ChangeSet created (ID: gxy13m673kmhr4vdtpu0ltwf)
   https://aws.amazon.com/marketplace/management/requests/gxy13m673kmhr4vdtpu0ltwf

This request will generate an offer ID associated with the product ID. An offer ID is **required** generate pricing template file for updating instance types.

.. note::

       For an existing published listing, an offer ID can also be obtained from the AWS console under :guilabel:`AWS Marketplace` > :guilabel:`Manage subscriptions`. Select the required listing and look for the `Offer ID` under `Agreement`.

       If you are in the draft stage, after running this command go to your generated request and check the :guilabel:`Entities` section under :guilabel:`Change request summary`.


Add/Edit product description
----------------------------

Once a product ID is created, you can add/edit the product description. The description fields are shown
below or you can also refer to the sample config file (listing_configuration.yaml)

.. code-block:: yaml
   :caption: listing_configuration.yaml

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

For empty values, use ``~`` for str type and ``[]`` for List type

To add/edit the product description, run:

.. code-block:: sh

   awsmp public-offer update-description \
      --product-id prod-xwpv7txqxg55e \
      --config listing_configuration.yaml

If a field value does not match the required format, it will show up as an error.


Update/Add instance type
------------------------

To update/add an instance type, you need to generate an instance type file and provide it as input while updating the listing.

#. Generate an instance type file (.csv) and provide as input file when updating listing.

   *example instance_type.csv*

   .. code-block::

      m7a.8xlarge,0.00,0.00
      m7a.large,0.00,0.00
      m7a.medium,0.00,0.00
      m7a.xlarge,0.00,0.00
      m7i-flex.8xlarge,0.00,0.00
      m7i-flex.large,0.00,0.00
      m7i-flex.xlarge,0.00,0.00

   You can generate an instance type file in two ways:

   #. Using the public-offer command

      If you've created new listing, you can use it's architecture and virtual type to run:

      .. code-block:: sh

            awsmp public-offer instance-type-template \
               --arch x86_64 \
               --virt hvm

      This command will create an ``instance_type.csv`` file. You can add/remove instance types in it as required.

   #. Using :guilabel:`pricing-template` command

      To get the existing instance type details, you can also run the following command. It required an offer ID as input (obtained while creating the product ID)
      and generates a prices.csv file. You can append additional instance types at the end of this file and use it as the instance type file while updating the instance type in the next step.

      .. code-block:: sh

         awsmp pricing-template \
            --offer-id offer-rsf4l7ilje2ze \
            --pricing prices.csv \
            --free


#. Using the generated instance type file, update the listing with one of the commands below.

   #. Free listing update

      .. code-block:: sh

         awsmp public-offer update-instance-type \
            --product-id prod-xwpv7txqxg55e \
            --instance-type-file instance_type.csv \
            --dimension-unit Hrs \
            --free Y
         
   #. Paid listing update

      .. code-block:: sh

         awsmp public-offer update-instance-type \
            --product-id prod-xwpv7txqxg55e \
            --instance-type-file instance_type.csv \
            --dimension-unit Hrs \
            --free N

Here, ``dimension-unit`` is the billing unit type for the product. For free listing, use ``Hrs``.

Different types are possible, but the currently available types are ``Hrs`` and ``Units``.


Update/Add region
-----------------

To add or update region information of an AMI product listing, use a configuration file with region details and the ``update-region`` option.

.. code-block:: yaml
   :caption: example listing_configuration.yaml

   ...
   region:
      commercial_regions: List[str]
      future_region_support_region: bool
   ...

Update the region using:

.. code-block:: sh

   awsmp public-offer update-region \
      --product-id prod-xwpv7txqxg55e \
      --config listing_configuration.yaml

GovCloud regions can't be enabled using the API. You'll need to contact a marketplace representative for gov region enablement

Add new version
---------------

To add new AMI version to an existing AMI listing, create a version configuration file and use the ``update-version`` option. A sample version configuration file (listing_configuration.yaml) looks like:

.. code-block:: yaml
   :caption: example listing_configuration.yaml

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

Add the new version using:

.. code-block:: sh

   awsmp public-offer update-version \
      --product-id prod-xwpv7txqxg55e \
      --config listing_configuration.yaml

Update legal/support terms
--------------------------

To update the legal/support terms of the AMI product listing, you'll need an offer ID and a yaml file with the required terms specified in it.

.. code-block:: yaml
   :caption: example listing_configuration.yaml

   ...
   eula_url: "https://eula-example"
   refund_policy: |
      Absolutely no refund!
   ...

Here, ``refund_policy`` contains free form of text.

To update the legal terms, use:

.. code-block:: sh

   awsmp public-offer update-legal-terms \
      --product-id prod-xwpv7txqxg55e \
      --config listing_configuration.yaml

To update support terms, use:

.. code-block:: sh

   awsmp public-offer update-support-terms \
      --product-id prod-xwpv7txqxg55e \
      --config listing_configuration.yaml

Release AMI product listing
---------------------------

To publish drafted AMI listing to :guilabel:`Limited` state, product ID and public offer ID are required:

.. code-block:: sh

   awsmp public-offer release \
      --product-id prod-fwu3xsqup23cs



Update AMI product listing details
----------------------------------

To update AMI product listing with multiple requests for product details (Description and Region Availability), run the command below, passing the product ID and product configuration file:

.. code-block:: sh

   awsmp public-offer update \
      --product-id prod-fwu3xsqup23cs
      --config listing_configuration.yaml


.. _`AWS marketplace management portal`: https://aws.amazon.com/marketplace/management/
