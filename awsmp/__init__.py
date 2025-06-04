from collections import defaultdict
from typing import TypedDict

from .models import InstanceTypePricing

InstanceTypeMapping = dict[str, list[InstanceTypePricing]]
INSTANCE_SIZE_TO_SCORE = {
    "nano": 1,
    "micro": 2,
    "small": 3,
    "medium": 4,
    "large": 5,
}


def sort_instance_types(instance_types: list[InstanceTypePricing]) -> list[InstanceTypePricing]:
    instance_types_by_family = defaultdict(list)
    sorted_instance_types = []
    for i in instance_types:
        family = i["name"].split(".")[0]
        instance_types_by_family[family].append(i)

    for family in sorted(instance_types_by_family):
        sorted_instance_types.extend(
            sorted(instance_types_by_family[family], key=lambda x: _get_instance_size_score(x["name"]))
        )

    return sorted_instance_types


def _get_instance_size_score(instance_type: str) -> int:
    _, instance_type_size = instance_type.split(".")
    score = -1
    if "metal" in instance_type_size:
        score = 1000
        if xl := instance_type_size.lstrip("metal-"):
            score += int(xl.rstrip("xl"))
    else:
        score = _get_non_metal_instance_type_score(instance_type)

    return score


def _get_non_metal_instance_type_score(instance_type: str) -> int:
    _, instance_type_size = instance_type.split(".")
    score = INSTANCE_SIZE_TO_SCORE.get(instance_type_size)

    if "xlarge" in instance_type_size:
        # base score for xlarge is 6. add preceding to sizing
        score = 6
        prefix = instance_type_size.rstrip("xlarge")
        if prefix:
            score += int(prefix)

    if not score:
        raise ValueError(f"Instance type size ({instance_type}) cannot be inferred")

    return score


def insert_type(
    instance_type: InstanceTypePricing, instance_types: list[InstanceTypePricing]
) -> list[InstanceTypePricing]:
    instance_types.append(instance_type)
    return sort_instance_types(instance_types)


__all__ = ["awsmp"]
