## ADDED Requirements

### Requirement: Add answer to post
The system SHALL provide an `add_answer(post_path: Path, author: str, body: str) -> StackPost` function in `src/lexibrary/stack/mutations.py` that:
- Parses the existing post from disk
- Appends a new `StackAnswer` with the next answer number, today's date, the given author and body
- Re-serializes and writes the post back to disk
- Returns the updated `StackPost`

#### Scenario: Add first answer
- **WHEN** `add_answer()` is called on a post with no existing answers
- **THEN** the new answer SHALL be `A1` with `number=1`

#### Scenario: Add second answer
- **WHEN** `add_answer()` is called on a post that already has `A1`
- **THEN** the new answer SHALL be `A2` with `number=2`

#### Scenario: Existing answers preserved
- **WHEN** `add_answer()` is called on a post with existing answers
- **THEN** all existing answers and their comments SHALL be preserved unchanged

### Requirement: Record vote on post or answer
The system SHALL provide a `record_vote(post_path: Path, target: str, direction: str, author: str, comment: str | None = None) -> StackPost` function that:
- `target` is `"post"` or `"A{n}"` (e.g., `"A1"`, `"A2"`)
- `direction` is `"up"` or `"down"`
- For `target="post"`: increments/decrements the post's `votes` field in frontmatter
- For `target="A{n}"`: increments/decrements the answer's `votes` field
- If `comment` is provided, appends a comment line with `[upvote]` or `[downvote]` context
- Downvotes (direction="down") SHALL require a non-None comment; the function SHALL raise `ValueError` if comment is None for a downvote

#### Scenario: Upvote post
- **WHEN** `record_vote(path, "post", "up", "agent-123")` is called on a post with `votes=3`
- **THEN** the post's `votes` SHALL become `4`

#### Scenario: Downvote post with comment
- **WHEN** `record_vote(path, "post", "down", "agent-123", comment="Incorrect")` is called on a post with `votes=3`
- **THEN** the post's `votes` SHALL become `2`

#### Scenario: Downvote without comment raises error
- **WHEN** `record_vote(path, "post", "down", "agent-123", comment=None)` is called
- **THEN** a `ValueError` SHALL be raised

#### Scenario: Upvote answer
- **WHEN** `record_vote(path, "A1", "up", "agent-123")` is called on a post where A1 has `votes=0`
- **THEN** A1's `votes` SHALL become `1`

#### Scenario: Downvote answer appends comment
- **WHEN** `record_vote(path, "A2", "down", "agent-123", comment="Doesn't work")` is called
- **THEN** A2's `votes` SHALL be decremented and a comment with `[downvote]` context SHALL be appended to A2's comments

#### Scenario: Upvote with optional comment
- **WHEN** `record_vote(path, "A1", "up", "agent-123", comment="Confirmed working")` is called
- **THEN** A1's `votes` SHALL be incremented and a comment with `[upvote]` context SHALL be appended

### Requirement: Accept answer
The system SHALL provide an `accept_answer(post_path: Path, answer_num: int) -> StackPost` function that:
- Sets the specified answer's `accepted` field to `True`
- Sets the post's `status` to `"resolved"`
- Re-serializes and writes the post back to disk

#### Scenario: Accept answer marks resolved
- **WHEN** `accept_answer(path, 1)` is called
- **THEN** A1 SHALL have `accepted=True` and the post SHALL have `status="resolved"`

#### Scenario: Accept nonexistent answer raises error
- **WHEN** `accept_answer(path, 99)` is called and no A99 exists
- **THEN** a `ValueError` SHALL be raised

### Requirement: Mark post as duplicate
The system SHALL provide a `mark_duplicate(post_path: Path, duplicate_of: str) -> StackPost` function that sets `status="duplicate"` and `duplicate_of` to the provided `ST-NNN` value.

#### Scenario: Mark duplicate
- **WHEN** `mark_duplicate(path, "ST-005")` is called
- **THEN** the post SHALL have `status="duplicate"` and `duplicate_of="ST-005"`

### Requirement: Mark post as outdated
The system SHALL provide a `mark_outdated(post_path: Path) -> StackPost` function that sets `status="outdated"`.

#### Scenario: Mark outdated
- **WHEN** `mark_outdated(path)` is called on a post with `status="open"`
- **THEN** the post SHALL have `status="outdated"`
