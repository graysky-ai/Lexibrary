"""Mutation functions for Stack posts — add answers, vote, accept, mark status."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from lexibrary.stack.models import StackAnswer, StackPost
from lexibrary.stack.parser import parse_stack_post
from lexibrary.stack.serializer import serialize_stack_post


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


def add_answer(post_path: Path, author: str, body: str) -> StackPost:
    """Append a new answer to a Stack post.

    The new answer receives the next sequential number (max existing + 1,
    or 1 if there are no answers yet), today's date, and the provided
    author and body text.

    Returns the updated StackPost after writing to disk.
    """
    post = _load_post(post_path)

    next_num = max((a.number for a in post.answers), default=0) + 1

    new_answer = StackAnswer(
        number=next_num,
        date=date.today(),
        author=author,
        votes=0,
        accepted=False,
        body=body,
        comments=[],
    )
    post.answers.append(new_answer)

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
    """Record an upvote or downvote on a post or answer.

    Args:
        post_path: Path to the stack post file.
        target: ``"post"`` or ``"A{n}"`` (e.g. ``"A1"``).
        direction: ``"up"`` or ``"down"``.
        author: Identifier of the voter.
        comment: Optional comment. **Required** for downvotes.

    Raises:
        ValueError: If direction is ``"down"`` and comment is None,
            or if the target answer does not exist.
    """
    if direction == "down" and comment is None:
        msg = "Downvotes require a comment"
        raise ValueError(msg)

    post = _load_post(post_path)
    delta = 1 if direction == "up" else -1

    if target == "post":
        post.frontmatter.votes += delta
        if comment is not None:
            tag = "[upvote]" if direction == "up" else "[downvote]"
            # For post-level votes with comments, we don't have an answer
            # to attach to — the spec only mentions answer comments, but
            # we still record the vote on the frontmatter votes field.
    else:
        # target is "A{n}"
        answer_num = _parse_answer_target(target)
        answer = _find_answer(post, answer_num)
        answer.votes += delta
        if comment is not None:
            tag = "[upvote]" if direction == "up" else "[downvote]"
            answer.comments.append(f"{tag} {author}: {comment}")

    _save_post(post_path, post)
    return _load_post(post_path)


def accept_answer(post_path: Path, answer_num: int) -> StackPost:
    """Mark an answer as accepted and set the post status to resolved.

    Raises:
        ValueError: If the specified answer number does not exist.
    """
    post = _load_post(post_path)
    answer = _find_answer(post, answer_num)
    answer.accepted = True
    post.frontmatter.status = "resolved"

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_answer_target(target: str) -> int:
    """Parse an answer target like ``'A1'`` into an integer."""
    if not target.startswith("A"):
        msg = f"Invalid answer target: {target!r}. Expected 'A{{n}}' format."
        raise ValueError(msg)
    try:
        return int(target[1:])
    except ValueError:
        msg = f"Invalid answer target: {target!r}. Expected 'A{{n}}' format."
        raise ValueError(msg) from None


def _find_answer(post: StackPost, answer_num: int) -> StackAnswer:
    """Find an answer by number, raising ValueError if not found."""
    for answer in post.answers:
        if answer.number == answer_num:
            return answer
    msg = f"Answer A{answer_num} not found in post {post.frontmatter.id}"
    raise ValueError(msg)
