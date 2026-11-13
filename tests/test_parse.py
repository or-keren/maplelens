import pytest

from maplelens.readers import ExpValue
from maplelens.readers.exp import parse_exp
from maplelens.readers.level import parse_level


def test_parse_exp():
    assert parse_exp("23,605 81.45%") == ExpValue(23605, 81.45)
    assert parse_exp("0 0.00%") == ExpValue(0, 0.0)


@pytest.mark.parametrize(
    "text",
    [
        "23,6",
        "81.4",
        "1 100.00%",
        "1 81.4%",
        ", 50.00%",
        "1,,2 5.00%",
        "23605 81.45%",
        "2,3605 81.45%",
        "23,60581.45%",
        "23,605 81.45",
        "",
    ],
)
def test_parse_exp_rejects(text):
    assert parse_exp(text) is None


def test_parse_level():
    assert parse_level("45") == 45
    assert parse_level("200") == 200


@pytest.mark.parametrize("text", ["0", "201", "", "4a"])
def test_parse_level_rejects(text):
    assert parse_level(text) is None
