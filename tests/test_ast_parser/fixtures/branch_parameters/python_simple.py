"""Fixture: simple if with a parameter in the condition."""


def process(data, flag):
    if flag:
        return data.upper()
    return data
