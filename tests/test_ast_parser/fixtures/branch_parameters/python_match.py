"""Fixture: match statement with a parameter as the subject."""


def handle(action):
    match action:
        case "start":
            return 1
        case "stop":
            return 0
        case _:
            return -1
