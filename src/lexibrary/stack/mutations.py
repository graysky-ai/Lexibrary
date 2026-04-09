"""Mutation functions for Stack posts — add findings, vote, accept, mark status."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from lexibrary.artifacts.ids import next_artifact_id
from lexibrary.artifacts.slugs import slugify
from lexibrary.stack.models import StackFinding, StackPost
from lexibrary.stack.parser import parse_stack_post
from lexibrary.stack.serializer import serialize_stack_post
from lexibrary.stack.template import render_post_template
from lexibrary.utils.atomic import atomic_write


def create_stack_post(
    stack_dir: Path,
    *,
    title: str,
    tags: list[str],
    author: str,
    bead: str | None = None,
    problem: str | None = None,
    context: str | None = None,
    evidence: list[str] | None = None,
    attempts: list[str] | None = None,
    refs_files: list[str] | None = None,
    refs_concepts: list[str] | None = None,
) -> Path:
    """Create a new Stack post file and return its path.

    Generates the next sequential ID (e.g. ``ST-001``), derives a filesystem-safe
    slug from the title, renders the post template, and writes the file atomically
    to *stack_dir*.

    Args:
        stack_dir: Directory where Stack post files are stored (typically
            ``.lexibrary/stack/``).  Created if it does not exist.
        title: Human-readable title for the post.
        tags: One or more tag strings to categorise the post.
        author: Identifier of the author creating the post.
        bead: Optional bead ID to associate with the post.
        problem: Optional problem description body text.
        context: Optional context section text.
        evidence: Optional list of evidence items.
        attempts: Optional list of attempted solutions.
        refs_files: Optional list of source file references.
        refs_concepts: Optional list of concept references.

    Returns:
        The :class:`~pathlib.Path` of the newly created post file.
    """
    post_id = next_artifact_id("ST", stack_dir, "ST-*-*.md")
    slug = slugify(title)
    filename = f"{post_id}-{slug}.md"
    post_path = stack_dir / filename

    content = render_post_template(
        post_id=post_id,
        title=title,
        tags=tags,
        author=author,
        bead=bead,
        refs_files=refs_files,
        refs_concepts=refs_concepts,
        problem=problem,
        context=context,
        evidence=evidence,
        attempts=attempts,
    )
    atomic_write(post_path, content)
    return post_path


def _load_post(post_path: Path) -> StackPost:
    """Parse a post from disk, raising ValueError if not found or invalid."""
    post = parse_stack_post(post_path)
    if post is None:
        msg = f"Cannot parse stack post at {post_path}"
        raise ValueError(msg)
    return post


def _save_post(post_path: Path, post: StackPost) -> None:
    """Serialize and write a post back to disk."""
    content = serialize_stack_post(post)
    post_path.write_text(content, encoding="utf-8")


def add_finding(post_path: Path, author: str, body: str) -> StackPost:
    """Append a new finding to a Stack post.

    The new finding receives the next sequential number (max existing + 1,
    or 1 if there are no findings yet), today's date, and the provided
    author and body text.

    Returns the updated StackPost after writing to disk.
    """
    post = _load_post(post_path)

    next_num = max((f.number for f in post.findings), default=0) + 1

    new_finding = StackFinding(
        number=next_num,
        date=date.today(),
        author=author,
        votes=0,
        accepted=False,
        body=body,
        comments=[],
    )
    post.findings.append(new_finding)

    _save_post(post_path, post)
    # Re-parse to ensure raw_body is consistent
    return _load_post(post_path)


def record_vote(
    post_path: Path,
    target: str,
    direction: str,
    author: str,
    comment: str | None = None,
) -> StackPost:
    """Record an upvote or downvote on a post or finding.

    Args:
        post_path: Path to the stack post file.
        target: ``"post"`` or ``"F{n}"`` (e.g. ``"F1"``).
        direction: ``"up"`` or ``"down"``.
        author: Identifier of the voter.
        comment: Optional comment. **Required** for downvotes.

    Raises:
        ValueError: If direction is ``"down"`` and comment is None,
            or if the target finding does not exist.
    """
    if direction == "down" and comment is None:
        msg = "Downvotes require a comment"
        raise ValueError(msg)

    post = _load_post(post_path)

    # Rate-limit: enforce 60-second cooldown between votes
    now = datetime.now(tz=UTC)
    if post.frontmatter.last_vote_at is not None:
        last_vote = post.frontmatter.last_vote_at
        if last_vote.tzinfo is None:
            last_vote = last_vote.replace(tzinfo=UTC)
        elapsed = (now - last_vote).total_seconds()
        if elapsed < 60:
            remaining = int(60 - elapsed)
            msg = (
                f"Vote rate-limited: please wait {remaining}s "
                f"before voting again on {post.frontmatter.id}"
            )
            raise ValueError(msg)

    delta = 1 if direction == "up" else -1

    if target == "post":
        post.frontmatter.votes += delta
        if comment is not None:
            tag = "[upvote]" if direction == "up" else "[downvote]"
            # For post-level votes with comments, we don't have a finding
            # to attach to — the spec only mentions finding comments, but
            # we still record the vote on the frontmatter votes field.
    else:
        # target is "F{n}"
        finding_num = _parse_finding_target(target)
        finding = _find_finding(post, finding_num)
        finding.votes += delta
        if comment is not None:
            tag = "[upvote]" if direction == "up" else "[downvote]"
            finding.comments.append(f"{tag} {author}: {comment}")

    # Record vote timestamp for rate-limiting
    post.frontmatter.last_vote_at = now

    _save_post(post_path, post)
    return _load_post(post_path)


def accept_finding(
    post_path: Path,
    finding_num: int,
    resolution_type: str | None = None,
) -> StackPost:
    """Mark a finding as accepted and set the post status to resolved.

    Args:
        post_path: Path to the stack post file.
        finding_num: The finding number to accept.
        resolution_type: Optional resolution type (e.g. ``"fix"``,
            ``"workaround"``). When provided, sets
            ``post.frontmatter.resolution_type``.

    Raises:
        ValueError: If the specified finding number does not exist.
    """
    post = _load_post(post_path)
    finding = _find_finding(post, finding_num)
    finding.accepted = True
    post.frontmatter.status = "resolved"
    if resolution_type is not None:
        post.frontmatter.resolution_type = resolution_type  # type: ignore[assignment]

    _save_post(post_path, post)
    return _load_post(post_path)


def mark_duplicate(post_path: Path, duplicate_of: str) -> StackPost:
    """Mark a post as a duplicate of another post.

    Args:
        duplicate_of: The ST-NNN identifier of the original post.
    """
    post = _load_post(post_path)
    post.frontmatter.status = "duplicate"
    post.frontmatter.duplicate_of = duplicate_of

    _save_post(post_path, post)
    return _load_post(post_path)


def mark_outdated(post_path: Path) -> StackPost:
    """Mark a post as outdated."""
    post = _load_post(post_path)
    post.frontmatter.status = "outdated"

    _save_post(post_path, post)
    return _load_post(post_path)


def mark_stale(post_path: Path) -> StackPost:
    """Mark a resolved post as stale.

    Only posts with ``status="resolved"`` can be marked stale.  Sets
    ``status`` to ``"stale"`` and ``stale_at`` to the current UTC
    timestamp in ISO format.

    Returns the updated :class:`StackPost` after writing to disk.

    Raises:
        ValueError: If the post does not have ``status="resolved"``.
    """
    post = _load_post(post_path)
    if post.frontmatter.status != "resolved":
        msg = (
            f"Only resolved posts can be marked stale (post {post.frontmatter.id} "
            f"has status={post.frontmatter.status!r})"
        )
        raise ValueError(msg)

    post.frontmatter.status = "stale"
    post.frontmatter.stale_at = datetime.now(tz=UTC)

    _save_post(post_path, post)
    return _load_post(post_path)


def mark_unstale(post_path: Path) -> StackPost:
    """Reverse staleness — set a stale post back to resolved.

    Only posts with ``status="stale"`` can be un-staled.  Sets
    ``status`` back to ``"resolved"`` and clears ``stale_at`` to
    ``None``.

    Returns the updated :class:`StackPost` after writing to disk.

    Raises:
        ValueError: If the post does not have ``status="stale"``.
    """
    post = _load_post(post_path)
    if post.frontmatter.status != "stale":
        msg = (
            f"Only stale posts can be un-staled (post {post.frontmatter.id} "
            f"has status={post.frontmatter.status!r})"
        )
        raise ValueError(msg)

    post.frontmatter.status = "resolved"
    post.frontmatter.stale_at = None

    _save_post(post_path, post)
    return _load_post(post_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_finding_target(target: str) -> int:
    """Parse a finding target like ``'F1'`` into an integer."""
    if not target.startswith("F"):
        msg = f"Invalid finding target: {target!r}. Expected 'F{{n}}' format."
        raise ValueError(msg)
    try:
        return int(target[1:])
    except ValueError:
        msg = f"Invalid finding target: {target!r}. Expected 'F{{n}}' format."
        raise ValueError(msg) from None


def _find_finding(post: StackPost, finding_num: int) -> StackFinding:
    """Find a finding by number, raising ValueError if not found."""
    for finding in post.findings:
        if finding.number == finding_num:
            return finding
    msg = f"Finding F{finding_num} not found in post {post.frontmatter.id}"
    raise ValueError(msg)
