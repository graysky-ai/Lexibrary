"""Wiki module — concept file parser, serializer, template, and resolver utilities."""

from __future__ import annotations

from lexibrary.wiki.index import ConceptIndex
from lexibrary.wiki.parser import parse_concept_file
from lexibrary.wiki.resolver import ResolvedLink, UnresolvedLink, WikilinkResolver
from lexibrary.wiki.serializer import serialize_concept_file
from lexibrary.wiki.template import concept_file_path, render_concept_template

__all__ = [
    "ConceptIndex",
    "ResolvedLink",
    "UnresolvedLink",
    "WikilinkResolver",
    "parse_concept_file",
    "serialize_concept_file",
    "render_concept_template",
    "concept_file_path",
]
