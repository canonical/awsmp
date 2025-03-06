How to manage an offer
======================

To manage existing offers in `AWS marketplace management portal`_, use the API calls described below.


Identify differences in public offer
------------------------------------

Before requesting changes to a public offer, compare the listing information in the `AWS marketplace management portal`_ with
the local configuration file to avoid unnecessary modifications.

The CLI command below will display the differences in product details, including description details and region availability.

To identify the differences, run:

.. code-block::

   $ awsmp inspect entity-diff prod-1234 local-config.yaml
   {
        "added": [
            {
                "name": "Videos",
                "value": ["https://video-url"],
            }
        ],
        "removed": [],
        "changed": [
            {
                "name": "Highlights",                         
                "old_value": ["test_highlight_1"],
                "new_value": ["test_highlight_1", "test_highlight_2"],
            },
        ],
    },
    ... output stripped here ...

The output shows the fields in ``local-config.yaml`` that have different values compared to the public listing.


.. _`AWS marketplace management portal`: https://aws.amazon.com/marketplace/management/
