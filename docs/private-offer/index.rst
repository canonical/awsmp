Private Offer
=============

To create a private offer in the `AWS marketplace management portal`_, use the API calls described below.


Listing and showing available offers
------------------------------------

Available offers can be listed:

.. code-block::

   $ awsmp entity-list Offer
   +---------------------------+------+------------+----------------------+
   |         entity-id         | name | visibility |     last-changed     |
   +---------------------------+------+------------+----------------------+
   | a8t4vhju1o9ibx6hfi9bnuo2x |  ''  |   Public   | 2021-09-03T08:14:37Z |
   +---------------------------+------+------------+----------------------+

Details about an available offer can be seen using the ``enitity-id``:

.. code-block::

   $ awsmp entity-show a8t4vhju1o9ibx6hfi9bnuo2x
   {'AgreementToken': 'sample-agreement-token',
    'Description': 'Worldwide offer for JUST FOR TESTING',
    'Id': 'a8t4vhju1o9ibx6hfi9bnuo2x',
    'MarkupPercentage': None,
    'Name': None,
    ... output stripped here ...


Creating a new private offer
----------------------------

A new private offer can be created with:

.. code-block:: sh

   $ awsmp private-offer create \
       --product-id 3a628887-30de-4d23-a949-93b32e4e4c5f \
       --buyer-accounts 887450378614 \
       --offer-name "toabctl testing" \
       --pricing prices.csv

   ChangeSet created (ID: 1mlxbdpmabfauymeeo12hg599)
   https://aws.amazon.com/marketplace/management/requests/1mlxbdpmabfauymeeo12hg599


This creates a new request in the AWS Marketplace web UI.
That new request needs to be in the ``Succeeded`` state before a buyer can see the offer.

For this command to work, you'll need a ``prices.csv`` file that contains all the
instance types (dimensions) and prices available in the product.

Generating a ``prices.csv`` file
--------------------------------

The ``awsmp private-offer create`` command requires a ``prices.csv`` file to be available.
That file contains 3 columns where the first column is the instance type, the
second column is the hourly price (in USD) and the third column is the annual price.

You can use a file from an existing offer and adjust it to generate
a new offer. To generate the file from an existing offer, run:

.. code-block:: sh

   awsmp pricing-template \
       --offer-id offer-rsf4l7ilje2ze \
       --pricing prices.csv

This creates a ``prices.csv`` file from the offer with the entity Id ``offer-rsf4l7ilje2ze``.

.. _`AWS marketplace management portal`: https://aws.amazon.com/marketplace/partners/management-tour?ref_=header_modules_sell_in_aws