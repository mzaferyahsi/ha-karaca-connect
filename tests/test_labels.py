"""Friendly names for raw API codes."""

import pytest

from custom_components.karaca_connect.labels import humanize, mode_name, mode_state_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("teabrewing", "Tea brewing"),
        ("boilingwater", "Boiling water"),
        ("filtercoffee", "Filter coffee"),
        ("babyfood", "Baby food"),
        ("standby", "Standby"),
        ("TeaBrewing", "Tea brewing"),
        ("somethingnew", "Somethingnew"),
        (None, None),
    ],
)
def test_mode_name(raw, expected):
    assert mode_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("brewedfresh", "Fresh"),
        ("brewedstale", "Stale"),
        ("brewing", "Brewing"),          # unseen, split by vocabulary
        ("waterboiled", "Water boiled"),
        ("keepwarm", "Keep warm"),
        ("xyz123", "Xyz123"),            # unknown: left readable, never dropped
    ],
)
def test_mode_state_name(raw, expected):
    assert mode_state_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("COOKING", "Cooking"), ("PRE_HEATING", "Pre heating"), ("preHeating", "Pre heating"), ("", None)],
)
def test_humanize(raw, expected):
    assert humanize(raw) == expected
