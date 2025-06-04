# type: ignore
import contextlib
import random

import pytest

from awsmp import _get_instance_size_score, insert_type, sort_instance_types

sorted_instance_types = [
    {"name": i}
    for i in [
        "a1.small",
        "a1.large",
        "a2.nano",
        "a2.micro",
        "a2.medium",
        "a2.large",
        "a2.2xlarge",
        "r6.nano",
        "r6.48xlarge",
        "r6.metal",
        "r6.metal-2xl",
        "r6.metal-48xl",
    ]
]


class TestInstanceSorting:
    @pytest.mark.parametrize(
        "instance_types", [random.sample(sorted_instance_types, len(sorted_instance_types)) for _ in range(10)]
    )
    def test_should_be_able_to_sort_types_by_size(self, instance_types):
        assert sort_instance_types(instance_types) == sorted_instance_types

    @pytest.mark.parametrize(
        "instance_type,expected_score",
        [
            ("a1.metal", 1000),
            ("a1.metal-2xl", 1002),
            ("a1.nano", 1),
            ("a1.micro", 2),
            ("a1.small", 3),
            ("a1.medium", 4),
            ("a1.large", 5),
            ("a1.xlarge", 6),
            ("a1.2xlarge", 8),
            ("a1.48xlarge", 54),
        ],
    )
    def test_should_be_able_to_score_instance_types(self, instance_type, expected_score):
        assert _get_instance_size_score(instance_type) == expected_score


class TestInsertInstanceTypeSuite:
    @pytest.mark.parametrize(
        "insert_size,expected",
        [
            ("metal-4xl", ["nano", "micro", "small", "medium", "large", "2xlarge", "metal", "metal-2xl", "metal-4xl"]),
            ("nano", ["nano", "micro", "small", "medium", "large", "2xlarge", "metal", "metal-2xl"]),
            ("4xlarge", ["nano", "micro", "small", "medium", "large", "2xlarge", "4xlarge", "metal", "metal-2xl"]),
        ],
    )
    def test_should_be_able_to_stable_insert_type(self, insert_size, expected):
        sizes = ["large", "metal", "metal-2xl", "micro", "medium", "small", "nano", "2xlarge"]
        with contextlib.suppress(Exception):
            sizes.remove(insert_size)
        expected = [{"name": f"a3.{size}"} for size in expected]

        instance_types = [{"name": f"a3.{size}"} for size in sizes]
        instance_type = {"name": f"a3.{insert_size}"}
        actual = insert_type(instance_type, instance_types)
        assert actual == expected
