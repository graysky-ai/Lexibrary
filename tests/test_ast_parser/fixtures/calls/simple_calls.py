"""Two top-level functions, one calling the other."""


def callee() -> int:
    return 1


def caller() -> int:
    return callee() + 1
