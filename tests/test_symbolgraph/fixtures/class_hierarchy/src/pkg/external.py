"""External (third-party) base — drives the ``class_edges_unresolved`` path.

``pydantic.BaseModel`` is deliberately a module that isn't in this fixture
project, so :class:`PythonResolver.resolve_class_name` returns ``None`` and
the builder records ``Thing → BaseModel`` as unresolved.
"""

from __future__ import annotations

from pydantic import BaseModel


class Thing(BaseModel):
    pass
