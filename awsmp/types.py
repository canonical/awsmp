from typing import Any, Dict, List, Literal, TypedDict, Union

from typing_extensions import NotRequired


class UpdateDimensionChange(TypedDict):
    Description: str  # Description shown on customer's billing
    Key: str  # Instance type name
    Name: str  # Instance type name
    Types: List[Literal["Metered"]]  # Dimension type. 'Metered' for AMI product
    Unit: Literal["Hrs", "Units"]  # Billing unit


class ChangeSetType(TypedDict):
    ChangeType: str
    ChangeName: NotRequired[str]
    Entity: Dict[str, str]
    DetailsDocument: Union[List[Dict[str, Any]], Dict[str, Any]]
    ChangeSetId: NotRequired[str]


class ChangeSetReturnType(TypedDict):
    ChangeSetArn: str
    ChangeSetId: str
