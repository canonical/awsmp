Installation
============

Setup profile configuration
---------------------------

Before using this tool, you need to setup the AWS configuration and credential files. Follow `CLI configuration documentation`_ to
create these two files.

Example config file:

.. code-block::

   $ cat ~/.aws/config
   [default]
   region = us-east-1

Example credential file:

.. code-block::

   $ cat ~/.aws/credentials 
   [default]
   aws_secret_access_key = $YOUR_SECRET_ACCESS_KEY
   aws_access_key_id = $YOUR_ACCESS_KEY_ID

Install awsmp using snap
------------------------

``awsmp`` is available in the `Snapstore`_, and it can be installed using:

.. code-block::

   snap install awsmp

This will install the latest version in your machine. We would highly recommend you to install the latest version, but refer to this `Snapcraft channel doc`_ for installing a different version or from channel.

CLI usage
----------

The command line interface called ``awsmp`` accepts the standard
AWS environment variables such as `AWS_PROFILE`. Note that Marketplace
interaction needs to happen in the `us-east-1` region (which is set
as the default in the CLI).

*awsmpcli is the legacy binary name, and is still available outside of snap builds.*

.. _`CLI configuration documentation`: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html#cli-configure-files-using-profiles
.. _`Snapstore`: https://snapcraft.io/awsmp
.. _`snapcraft channel doc`: https://snapcraft.io/docs/channels