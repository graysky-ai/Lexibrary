"""Integration tests for the AST parser public API: end-to-end hashing.

Tests cover:
- End-to-end hashing via compute_hashes() and hash_interface()
- Hash stability (same input produces same output)
- Hash sensitivity to signature changes
- Hash insensitivity to body/order changes
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from lexibrary.ast_parser import compute_hashes, hash_interface, parse_interface
from lexibrary.ast_parser.models import (
    ConstantSig,
    FunctionSig,
    InterfaceSkeleton,
    ParameterSig,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# End-to-end hashing: parse -> render -> hash
# ---------------------------------------------------------------------------


class TestEndToEndHashing:
    """Test the full pipeline: file -> skeleton -> hash."""

    def test_compute_hashes_python_fixture(self) -> None:
        """compute_hashes returns both content and interface hashes for .py."""
        fixture = FIXTURES_DIR / "simple_module.py"
        content_hash, interface_hash = compute_hashes(fixture)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64  # SHA-256 hex digest
        assert isinstance(interface_hash, str)
        assert len(interface_hash) == 64

    def test_compute_hashes_typescript_fixture(self) -> None:
        """compute_hashes returns both hashes for .ts files."""
        fixture = FIXTURES_DIR / "simple_module.ts"
        content_hash, interface_hash = compute_hashes(fixture)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64
        assert isinstance(interface_hash, str)
        assert len(interface_hash) == 64

    def test_compute_hashes_javascript_fixture(self) -> None:
        """compute_hashes returns both hashes for .js files."""
        fixture = FIXTURES_DIR / "simple_module.js"
        content_hash, interface_hash = compute_hashes(fixture)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64
        assert isinstance(interface_hash, str)
        assert len(interface_hash) == 64

    def test_compute_hashes_unsupported_extension(self, tmp_path: Path) -> None:
        """compute_hashes returns None interface_hash for unsupported files."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("Hello world")
        content_hash, interface_hash = compute_hashes(txt_file)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64
        assert interface_hash is None

    def test_parse_interface_returns_skeleton(self) -> None:
        """parse_interface returns an InterfaceSkeleton for supported files."""
        fixture = FIXTURES_DIR / "simple_module.py"
        skeleton = parse_interface(fixture)

        assert skeleton is not None
        assert isinstance(skeleton, InterfaceSkeleton)

    def test_parse_interface_unsupported_returns_none(self, tmp_path: Path) -> None:
        """parse_interface returns None for unsupported extensions."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("Hello world")
        result = parse_interface(txt_file)
        assert result is None

    def test_hash_interface_produces_digest(self) -> None:
        """hash_interface returns a valid SHA-256 hex digest."""
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(
                    name="greet",
                    parameters=[ParameterSig(name="name", type_annotation="str")],
                    return_type="str",
                ),
            ],
            classes=[],
            constants=[],
            exports=[],
        )
        digest = hash_interface(skeleton)
        assert isinstance(digest, str)
        assert len(digest) == 64


# ---------------------------------------------------------------------------
# Hash stability: same input -> same hash
# ---------------------------------------------------------------------------


class TestHashStability:
    """Verify that hashing is deterministic and stable."""

    def test_same_file_same_hash(self) -> None:
        """Parsing the same file twice produces identical hashes."""
        fixture = FIXTURES_DIR / "simple_module.py"
        _, hash1 = compute_hashes(fixture)
        _, hash2 = compute_hashes(fixture)
        assert hash1 == hash2

    def test_same_skeleton_same_hash(self) -> None:
        """Hashing equivalent skeletons produces identical digests."""
        skeleton = InterfaceSkeleton(
            file_path="test.py",
            language="python",
            functions=[
                FunctionSig(
                    name="foo",
                    parameters=[ParameterSig(name="x", type_annotation="int")],
                    return_type="int",
                ),
            ],
            classes=[],
            constants=[ConstantSig(name="BAR", type_annotation="str")],
            exports=[],
        )
        digest1 = hash_interface(skeleton)
        digest2 = hash_interface(skeleton)
        assert digest1 == digest2

    def test_rewritten_identical_file_same_hash(self, tmp_path: Path) -> None:
        """Writing the same source content to a new file produces the same interface hash."""
        source = dedent("""\
            MAX_RETRIES = 3

            def process(x: int) -> int:
                return x * 2
        """)
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source)
        file_b.write_text(source)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a == hash_b


# ---------------------------------------------------------------------------
# Hash sensitivity: signature changes -> different hash
# ---------------------------------------------------------------------------


class TestHashSensitivity:
    """Verify that signature changes produce different hashes."""

    def test_different_function_name_different_hash(self, tmp_path: Path) -> None:
        """Renaming a function changes the interface hash."""
        source_a = "def foo(x: int) -> int:\n    return x\n"
        source_b = "def bar(x: int) -> int:\n    return x\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a != hash_b

    def test_different_param_type_different_hash(self, tmp_path: Path) -> None:
        """Changing a parameter type changes the interface hash."""
        source_a = "def foo(x: int) -> int:\n    return x\n"
        source_b = "def foo(x: str) -> int:\n    return x\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a != hash_b

    def test_different_return_type_different_hash(self, tmp_path: Path) -> None:
        """Changing a return type changes the interface hash."""
        source_a = "def foo(x: int) -> int:\n    return x\n"
        source_b = "def foo(x: int) -> str:\n    return str(x)\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a != hash_b

    def test_added_parameter_different_hash(self, tmp_path: Path) -> None:
        """Adding a parameter changes the interface hash."""
        source_a = "def foo(x: int) -> int:\n    return x\n"
        source_b = "def foo(x: int, y: int) -> int:\n    return x + y\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a != hash_b

    def test_added_function_different_hash(self, tmp_path: Path) -> None:
        """Adding a new public function changes the interface hash."""
        source_a = "def foo() -> None:\n    pass\n"
        source_b = "def foo() -> None:\n    pass\n\ndef bar() -> None:\n    pass\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a != hash_b

    def test_added_constant_different_hash(self, tmp_path: Path) -> None:
        """Adding a constant changes the interface hash."""
        source_a = "def foo() -> None:\n    pass\n"
        source_b = "MAX_SIZE = 100\n\ndef foo() -> None:\n    pass\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a != hash_b


# ---------------------------------------------------------------------------
# Hash insensitivity: body/order changes -> same hash
# ---------------------------------------------------------------------------


class TestHashInsensitivity:
    """Verify that body and declaration order changes do NOT affect hashes."""

    def test_body_change_same_interface_hash(self, tmp_path: Path) -> None:
        """Changing function body without changing signature keeps same interface hash."""
        source_a = "def foo(x: int) -> int:\n    return x\n"
        source_b = "def foo(x: int) -> int:\n    result = x * 2\n    return result\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a == hash_b

    def test_reordered_functions_same_hash(self, tmp_path: Path) -> None:
        """Reordering functions does not change the interface hash."""
        source_a = dedent("""\
            def alpha() -> None:
                pass

            def beta() -> None:
                pass
        """)
        source_b = dedent("""\
            def beta() -> None:
                pass

            def alpha() -> None:
                pass
        """)

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a == hash_b

    def test_comment_change_same_interface_hash(self, tmp_path: Path) -> None:
        """Changing comments does not change the interface hash."""
        source_a = '# Old comment\ndef foo() -> None:\n    """Old doc."""\n    pass\n'
        source_b = '# New comment\ndef foo() -> None:\n    """New doc."""\n    pass\n'

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a == hash_b

    def test_whitespace_change_same_interface_hash(self, tmp_path: Path) -> None:
        """Adding blank lines between declarations does not change the interface hash."""
        source_a = "def foo() -> None:\n    pass\ndef bar() -> None:\n    pass\n"
        source_b = "def foo() -> None:\n    pass\n\n\n\ndef bar() -> None:\n    pass\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        _, hash_a = compute_hashes(file_a)
        _, hash_b = compute_hashes(file_b)
        assert hash_a == hash_b

    def test_content_hash_differs_but_interface_same(self, tmp_path: Path) -> None:
        """Body changes alter content_hash but not interface_hash."""
        source_a = "def foo(x: int) -> int:\n    return x\n"
        source_b = "def foo(x: int) -> int:\n    return x + 1\n"

        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text(source_a)
        file_b.write_text(source_b)

        content_a, iface_a = compute_hashes(file_a)
        content_b, iface_b = compute_hashes(file_b)

        # Content hashes differ (different bytes)
        assert content_a != content_b
        # Interface hashes are identical (same signature)
        assert iface_a == iface_b
