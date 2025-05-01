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

    product:
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


Update instance types and pricing
---------------------------------

To update instance types and pricing, you need to add offer field containing offer information of the listing. The sample config is described below.

#. For hourly pricing AMI Product:

.. code-block:: yaml
   :caption: listing_configuration.yaml

    offer:
        instance_types:
            - name: c3.large
              hourly: 0.12
            - name: c4.medium
              hourly: 0.08

#. For hourly and annual pricing AMI product:            

.. code-block:: yaml
   :caption: listing_configuration.yaml

    offer:
        instance_types:
            - name: c3.large
              yearly: 123.45
              hourly: 0.12
            - name: c4.medium
              yearly: 45.12
              hourly: 0.08

#. For hourly and monthly pricing AMI product:

.. code-block:: yaml
   :caption: listing_configuration.yaml

    offer:
        instance_types:
            - name: c3.large
              yearly: 123.45
              hourly: 0.12
            - name: c4.medium
              yearly: 45.12
              hourly: 0.08
        monthly_subscription_fee: 50.00


Once offer field is ready, run the command:

.. code-block:: sh

         awsmp public-offer update-instance-type \
            --product-id prod-xwpv7txqxg55e \
            --config listing_configuration.yaml \
            --dimension-unit Hrs \
            --allow-price-change


Different billing unit types are possible, but the currently supported types are ``Hrs`` and ``Units``.

The CLI retrieves the added and removed instance types from the configuration by comparing it with the existing listing, then sends the appropriate add/restrict instance type requests.
It also compares the pricing before sending a request to avoid unnecessary price changes (increases or decreases) in the listing. To update the price, pass the `--price_change-allowed` flag.

Update/Add region
-----------------

To add or update region information of an AMI product listing, use a configuration file with region details and the ``update-region`` option.

.. code-block:: yaml
   :caption: example listing_configuration.yaml

   ...
   product:
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
   product:
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

To update the legal/support terms of the AMI product listing, you'll need a yaml file with the required terms specified in the `offer` field.

.. code-block:: yaml
   :caption: example listing_configuration.yaml

   ...
   offer:
        eula_document:
            - type: "CustomEula"
              url: "https://eula-example"
        refund_policy: |
            Absolutely no refund!
   ...

A ``eula_document`` can contain only one item. To check the type and conditionally required field (either ``url`` or ``version``), refer to `AWS Marketplace update legal resources API reference`_.

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

To update AMI product listing with multiple requests for product details (Description, Region Availability, Instance types and Pricing information), run the command below, passing the product ID and product configuration file:

.. code-block:: sh

   awsmp public-offer update \
      --product-id prod-fwu3xsqup23cs
      --config listing_configuration.yaml


.. _`AWS marketplace management portal`: https://aws.amazon.com/marketplace/management/
.. _`AWS Marketplace update legal resources API reference`: https://docs.aws.amazon.com/marketplace/latest/APIReference/work-with-private-offers.html#update-legal-terms
