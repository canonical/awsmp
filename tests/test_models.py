import pytest

from awsmp import models


def build_ami_product(**kwargs):
    defaults = dict(
        product_title="p" * 72,
        short_description="short_description",
        long_description="long_descrption",
        logourl="https://some-url",
        highlights=["highlight1"],
        categories=["Storage"],
        search_keywords=["one_term"],
        support_description="supported!",
    )
    return models.AmiProduct(**(defaults | kwargs))


class TestAmiProductSuite:
    @pytest.mark.parametrize(
        "provided_keys,expected",
        [
            ([], []),
            ([{"some_key": "http://some_value"}], [{"Text": "some_key", "Url": "http://some_value/"}]),
            (
                [{f"k{i}": f"http://url{i}/"} for i in range(3)],
                [{"Text": f"k{i}", "Url": f"http://url{i}/"} for i in range(3)],
            ),
        ],
    )
    def test_should_convert_additional_resources_to_api_format(self, provided_keys, expected):
        product = build_ami_product(additional_resources=provided_keys)
        assert product.additional_resources == expected

    @pytest.mark.parametrize("ami_product_field", ["support_description", "long_description"])
    def test_should_strip_new_lines_from_relevent_fields(self, ami_product_field):
        valid_description = "my description\n\nafter separator"
        product = build_ami_product(**{ami_product_field: f"\n\n\n{valid_description}\n\n"})
        assert getattr(product, ami_product_field) == valid_description

    def test_search_keywords_should_not_accept_large_input(self):
        keywords = ["a" * 150, "b" * 105, "c", "d", "e"]
        with pytest.raises(ValueError) as e:
            build_ami_product(search_keywords=keywords)
        err = "Combined character count of keywords can be at most 250 characters"
        assert err in str(e.value)
