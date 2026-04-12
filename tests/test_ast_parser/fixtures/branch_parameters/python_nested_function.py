"""Fixture: parameter used only in an inner function's branch."""


def outer(data, mode):
    """The outer function does not branch on mode itself."""

    def inner(x):
        if mode:
            return x + 1
        return x

    return inner(data)
