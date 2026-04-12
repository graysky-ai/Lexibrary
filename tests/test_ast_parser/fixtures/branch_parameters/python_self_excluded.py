"""Fixture: self used in a branch condition should be excluded."""


class Processor:
    def run(self, data):
        if self.enabled:
            return data
        return None
