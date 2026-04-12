"""Fixture: attribute access on a parameter in a branch condition."""


def render(config):
    if config.verbose:
        print("verbose mode")
    return "done"
