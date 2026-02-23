"""Round-trip tests for Stack post serializer.

These tests serialize a StackPost, write the result to a temp file,
parse it back using the real parser, and verify equivalence.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from lexibrary.stack.models import (
    StackAnswer,
    StackPost,
    StackPostFrontmatter,
    StackPostRefs,
)
from lexibrary.stack.parser import parse_stack_post
from lexibrary.stack.serializer import serialize_stack_post

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_frontmatter(**overrides: object) -> StackPostFrontmatter:
    defaults: dict[str, object] = {
        "id": "ST-001",
        "title": "Test post",
        "tags": ["bug"],
        "created": date(2026, 2, 21),
        "author": "agent-123",
    }
    defaults.update(overrides)
    return StackPostFrontmatter(**defaults)  # type: ignore[arg-type]


def _roundtrip(post: StackPost, tmp_path: Path) -> StackPost:
    """Serialize a post, write to disk, and parse it back."""
    text = serialize_stack_post(post)
    path = tmp_path / "ST-001-test.md"
    path.write_text(text, encoding="utf-8")
    parsed = parse_stack_post(path)
    assert parsed is not None, "Parser returned None for serialized output"
    return parsed


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Verify serialize -> parse -> compare equivalence."""

    def test_roundtrip_no_answers(self, tmp_path: Path) -> None:
        original = StackPost(
            frontmatter=_make_frontmatter(),
            problem="Something is broken.",
            evidence=["Error line 1", "Error line 2"],
        )
        parsed = _roundtrip(original, tmp_path)

        assert parsed.frontmatter == original.frontmatter
        assert parsed.problem == original.problem
        assert parsed.evidence == original.evidence
        assert parsed.answers == []

    def test_roundtrip_with_answers_and_comments(self, tmp_path: Path) -> None:
        a1 = StackAnswer(
            number=1,
            date=date(2026, 2, 21),
            author="agent-456",
            votes=3,
            accepted=True,
            body="Use approach X.",
            comments=[
                "**2026-02-22 agent-789 [upvote]:** Confirmed this works.",
            ],
        )
        a2 = StackAnswer(
            number=2,
            date=date(2026, 2, 22),
            author="agent-789",
            votes=-1,
            body="Alternative approach Y.",
            comments=[
                "**2026-02-23 agent-123 [downvote]:** This is unreliable.",
            ],
        )
        original = StackPost(
            frontmatter=_make_frontmatter(
                refs=StackPostRefs(
                    concepts=["DateHandling"],
                    files=["src/foo.py"],
                    designs=["src/bar.py"],
                ),
                bead="lexibrary-abc.1",
                votes=5,
            ),
            problem="Date parsing fails in edge cases.",
            evidence=["ValueError on line 42", "Timezone mismatch"],
            answers=[a1, a2],
        )
        parsed = _roundtrip(original, tmp_path)

        assert parsed.frontmatter == original.frontmatter
        assert parsed.problem == original.problem
        assert parsed.evidence == original.evidence
        assert len(parsed.answers) == 2

        for orig_a, parsed_a in zip(original.answers, parsed.answers, strict=True):
            assert parsed_a.number == orig_a.number
            assert parsed_a.date == orig_a.date
            assert parsed_a.author == orig_a.author
            assert parsed_a.votes == orig_a.votes
            assert parsed_a.accepted == orig_a.accepted
            assert parsed_a.body == orig_a.body
            assert parsed_a.comments == orig_a.comments

    def test_roundtrip_all_fields(self, tmp_path: Path) -> None:
        """Fully populated StackPost round-trips faithfully."""
        original = StackPost(
            frontmatter=_make_frontmatter(
                id="ST-042",
                title="Complex scenario",
                tags=["perf", "config"],
                status="resolved",
                created=date(2026, 1, 15),
                author="agent-007",
                bead="lexibrary-xyz.5",
                votes=10,
                duplicate_of="ST-001",
                refs=StackPostRefs(
                    concepts=["Caching", "Retry"],
                    files=["src/cache.py", "src/retry.py"],
                    designs=["src/cache.py", "src/retry.py"],
                ),
            ),
            problem="Performance degrades under load.",
            evidence=["p99 latency >500ms", "CPU at 100%"],
            answers=[
                StackAnswer(
                    number=1,
                    date=date(2026, 1, 16),
                    author="agent-456",
                    votes=7,
                    accepted=True,
                    body="Add caching layer.",
                    comments=[
                        "**2026-01-17 agent-789 [upvote]:** Works great.",
                        "**2026-01-18 agent-007 [upvote]:** Deployed.",
                    ],
                ),
            ],
        )
        parsed = _roundtrip(original, tmp_path)

        assert parsed.frontmatter == original.frontmatter
        assert parsed.problem == original.problem
        assert parsed.evidence == original.evidence
        assert len(parsed.answers) == len(original.answers)
        assert parsed.answers[0] == original.answers[0]
