import pytest

from awsmp import changesets


@pytest.mark.parametrize(
    "eula_url,expected",
    [(None, {"Type": "StandardEula", "Version": "2022-07-14"}), ("foobar", {"Type": "CustomEula", "Url": "foobar"})],
)
def test_changeset_update_legal_terms_eula_options(eula_url, expected):
    result = changesets._changeset_update_legal_terms(eula_url=eula_url)
    result["Details"]["Terms"][0] == expected  # type: ignore
