"""Fixture: parameter appears only in an assert statement."""


def validate(value, expected):
    assert expected > 0
    return value * 2
