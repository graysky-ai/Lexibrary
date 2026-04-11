"""Attribute call fixture: logger, ConceptIndex.find, os.path.join."""

import logging
import os


class ConceptIndex:
    @staticmethod
    def find(name: str) -> int:
        return len(name)


def run() -> None:
    logger = logging.getLogger(__name__)
    logger.info("starting")
    ConceptIndex.find("x")
    os.path.join("a", "b")
