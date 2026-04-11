"""Pydantic BaseModel fixture: external base resolves to unresolved later."""

from pydantic import BaseModel


class X(BaseModel):
    pass
