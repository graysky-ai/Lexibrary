"""Shared wikilink and comment-stripping regex patterns.

All wikilink extraction and HTML-comment pre-processing regex lives here.
Consuming modules (linkgraph/builder, wiki/parser, validator/checks,
lifecycle/concept_deprecation) import from this module rather than
defining local patterns.

Future enhancement ST-005 (code-block exclusion) should be implemented
here when the time comes.
"""

from __future__ import annotations

import re

WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
"""Match ``[[target]]`` where target must not contain ``[`` or ``]``."""

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
"""Match HTML comments, including multi-line (uses ``re.DOTALL``)."""


def extract_wikilinks(text: str) -> list[str]:
    """Extract unique [[wikilink]] targets from text, ignoring HTML comments.

    Returns deduplicated names in order of first appearance.
    """
    cleaned = HTML_COMMENT_RE.sub("", text)
    seen: set[str] = set()
    result: list[str] = []
    for m in WIKILINK_RE.finditer(cleaned):
        name = m.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result
