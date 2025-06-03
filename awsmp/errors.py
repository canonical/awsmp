from typing import List


class MissingInstanceTypeError(Exception):
    def __init__(self, instance_types: List[str]):
        formatted_types = "\n".join(instance_types)
        message = f"The following instance types are missing from your pricing csv:\n{formatted_types}"
        super().__init__(message)


class AWSException(Exception):
    pass


class AccessDeniedException(AWSException):
    def __init__(self, service_name: str):
        message = f"""


This account does not have permission to request {service_name} services.
Check your IAM permission or seller registration if you use marketplace service.
"""
        super().__init__(message)


class ResourceNotFoundException(AWSException):
    def __init__(self, *args):
        if args:
            super().__init__(*args)
        else:
            message = """


Product/Offer ID does not exist. Please check your those information and try again.
Product/Offer ID can be found in Home > Requests > Create new AMI Product from marketplace management portal https://aws.amazon.com/marketplace/management/requests/.
"""
            super().__init__(message)


class UnrecognizedClientException(AWSException):
    def __init__(self):
        message = """


This profile is not configured correctly.
Please check your credential with associated profile.
"""
        super().__init__(message)


class ValidationException(AWSException):
    def __init__(self, error_msg):
        message = f"""


{error_msg}
Please check schema regex and request with fixed value.
"""
        super().__init__(message)


class YamlMissingKeyException(Exception):
    def __init__(self, missing_keys: List[List[str]]):
        formatted_keys = "\n".join("->".join(keys) for keys in missing_keys)
        message = f"""


Config file does not have the following missing keys:
{formatted_keys}.

Please check the file and request again.
"""
        super().__init__(message)


class NoProductIdProvidedException(Exception):
    def __init__(self):
        message = f"""


No product ids are provided. Please pass at least one product id for using this function.
"""
        super().__init__(message)


class AmiPriceChangeError(Exception):
    pass


class AmiPricingModelChangeError(Exception):
    pass


class NoVersionException(Exception):
    pass
