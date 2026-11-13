"""Dependency-free regression tests for scanner behavior and CLI exit codes."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / ".github" / "scripts" / "content_guard.py"
SPEC = importlib.util.spec_from_file_location("content_guard", GUARD_PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class ContentGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="content-guard-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.term = guard.FORBIDDEN_TERMS[0]

    def write(self, relative_path, content="Ordinary project content.\n"):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def scan(self, root=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = guard.check_content(self.root if root is None else root)
        return code, stdout.getvalue(), stderr.getvalue()

    def cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(GUARD_PATH), *map(str, args)],
            cwd=self.root if cwd is None else cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_empty_directory_passes(self):
        code, output, errors = self.scan()
        self.assertEqual(code, 0)
        self.assertIn("Scanned 0 text file(s)", output)
        self.assertEqual(errors, "")

    def test_clean_supported_files_pass(self):
        for extension in guard.TEXT_EXTENSIONS:
            self.write("clean" + extension)
        code, output, errors = self.scan()
        self.assertEqual(code, 0)
        self.assertIn("Scanned 5 text file(s)", output)
        self.assertEqual(errors, "")

    def test_every_forbidden_term_is_detected(self):
        for index, term in enumerate(guard.FORBIDDEN_TERMS):
            with self.subTest(term_index=index):
                self.write(f"term-{index}/file.md", term)
                code, output, _ = self.scan(self.root / f"term-{index}")
                self.assertEqual(code, 1)
                self.assertIn(repr(term), output)

    def test_every_supported_extension_is_checked(self):
        for extension in sorted(guard.TEXT_EXTENSIONS):
            with self.subTest(extension=extension):
                self.write("kind-" + extension[1:] + "/file" + extension, self.term)
                code, output, _ = self.scan(self.root / ("kind-" + extension[1:]))
                self.assertEqual(code, 1)
                self.assertIn("file" + extension, output)

    def test_uppercase_extensions_are_checked(self):
        self.write("policy.YaMl", self.term)
        self.assertEqual(self.scan()[0], 1)

    def test_all_violations_are_reported(self):
        self.write("first.md", "\n".join(guard.FORBIDDEN_TERMS))
        self.write("second.txt", self.term)
        code, output, _ = self.scan()
        self.assertEqual(code, 1)
        self.assertEqual(output.count("Violation:"), 3)

    def test_github_markdown_is_checked(self):
        self.write(".github/pull_request_template.md", self.term)
        code, output, _ = self.scan()
        self.assertEqual(code, 1)
        self.assertIn(".github/pull_request_template.md", output)

    def test_github_yaml_is_checked(self):
        self.write(".github/workflows/example.yaml", self.term)
        self.assertEqual(self.scan()[0], 1)

    def test_other_hidden_directories_are_checked(self):
        self.write(".config/policy.txt", self.term)
        self.assertEqual(self.scan()[0], 1)

    def test_git_directory_is_pruned(self):
        self.write(".git/objects/example.md", self.term)
        code, output, errors = self.scan()
        self.assertEqual(code, 0)
        self.assertIn("Scanned 0 text file(s)", output)
        self.assertEqual(errors, "")

    def test_nested_git_directory_is_pruned(self):
        self.write("nested/.git/private.yaml", b"\xff")
        self.assertEqual(self.scan()[0], 0)

    def test_git_substring_does_not_exclude_a_directory(self):
        self.write("project.git/document.md", self.term)
        self.assertEqual(self.scan()[0], 1)

    def test_git_metadata_file_is_not_a_text_target(self):
        self.write(".git", b"\xff")
        self.assertEqual(self.scan()[0], 0)

    def test_only_the_guard_itself_is_excluded(self):
        own_file = self.write("guard.py", self.term)
        self.write("other.py", self.term)
        with mock.patch.object(guard, "SCRIPT_PATH", own_file):
            code, output, _ = self.scan()
        self.assertEqual(code, 1)
        self.assertIn("Violation: other.py:", output)
        self.assertNotIn("Violation: guard.py:", output)
        self.assertIn("Scanned 1 text file(s)", output)

    def test_other_scripts_beside_the_guard_are_checked(self):
        self.write(".github/scripts/other.py", self.term)
        self.assertEqual(self.scan()[0], 1)

    def test_unsupported_file_types_are_not_read(self):
        self.write("image.bin", b"\xff" + self.term.encode())
        code, output, errors = self.scan()
        self.assertEqual(code, 0)
        self.assertIn("Scanned 0 text file(s)", output)
        self.assertEqual(errors, "")

    def test_unicode_text_passes(self):
        self.write("international.md", "Caf\u00e9 \u2014 \u65e5\u672c\u8a9e\n")
        self.assertEqual(self.scan()[0], 0)

    def test_invalid_utf8_is_an_error(self):
        self.write("invalid.md", b"\xff\xfe")
        code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("invalid.md", errors)
        self.assertIn("Scan incomplete", errors)

    def test_unreadable_file_is_an_error(self):
        self.write("private.md")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("private.md", errors)
        self.assertIn("denied", errors)

    def test_disappearing_file_is_an_error(self):
        self.write("vanished.md")
        with mock.patch.object(Path, "read_text", side_effect=FileNotFoundError("gone")):
            code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("vanished.md", errors)

    def test_walk_error_is_reported(self):
        def failed_walk(*args, **kwargs):
            kwargs["onerror"](PermissionError(13, "denied", str(self.root / "private")))
            return iter(())

        with mock.patch.object(guard.os, "walk", side_effect=failed_walk):
            code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("private", errors)

    def test_errors_take_precedence_over_violations(self):
        self.write("blocked.md", self.term)
        self.write("invalid.txt", b"\xff")
        code, output, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("Violation: blocked.md:", output)
        self.assertIn("invalid.txt", errors)

    def test_scanning_continues_after_a_read_error(self):
        self.write("a-invalid.txt", b"\xff")
        self.write("z-blocked.md", self.term)
        code, output, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("Violation: z-blocked.md:", output)
        self.assertIn("a-invalid.txt", errors)

    def test_missing_root_is_an_error(self):
        code, _, errors = self.scan(self.root / "missing")
        self.assertEqual(code, 2)
        self.assertIn("Cannot access scan root", errors)

    def test_file_root_is_an_error(self):
        code, _, errors = self.scan(self.write("not-a-directory.md"))
        self.assertEqual(code, 2)
        self.assertIn("Not a directory", errors)

    def test_symbolic_link_text_file_is_rejected(self):
        target = self.write("ordinary.txt")
        (self.root / "alias.md").symlink_to(target)
        code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("symbolic-link text file", errors)

    def test_symbolic_link_directory_is_rejected(self):
        target = self.root / "ordinary"
        target.mkdir()
        (self.root / "alias").symlink_to(target, target_is_directory=True)
        code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("symbolic-link directory", errors)

    def test_broken_symbolic_link_text_file_is_rejected(self):
        (self.root / "broken.md").symlink_to(self.root / "missing")
        self.assertEqual(self.scan()[0], 2)

    def test_nonregular_text_file_is_an_error(self):
        self.write("special.md")
        with mock.patch.object(Path, "is_file", return_value=False):
            code, _, errors = self.scan()
        self.assertEqual(code, 2)
        self.assertIn("Not a regular text file", errors)

    def test_unexpected_programming_errors_are_not_swallowed(self):
        self.write("ordinary.md")
        with mock.patch.object(Path, "read_text", side_effect=RuntimeError("bug")):
            with self.assertRaisesRegex(RuntimeError, "bug"):
                self.scan()

    def test_diagnostics_are_deterministic(self):
        self.write("z.md", self.term)
        self.write("a.md", self.term)
        _, output, _ = self.scan()
        self.assertLess(output.index("Violation: a.md:"), output.index("Violation: z.md:"))

    def test_scans_do_not_share_failure_state(self):
        self.write("blocked.md", self.term)
        clean_root = self.root / "clean"
        clean_root.mkdir()
        self.assertEqual(self.scan()[0], 1)
        self.assertEqual(self.scan(clean_root)[0], 0)

    def test_cli_defaults_to_current_directory(self):
        self.write("ordinary.md")
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scanned 1 text file(s)", result.stdout)

    def test_cli_returns_one_for_violations(self):
        self.write("blocked.md", self.term)
        result = self.cli(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Violation: blocked.md:", result.stdout)

    def test_cli_returns_two_for_scan_errors(self):
        self.write("invalid.md", b"\xff")
        result = self.cli(self.root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid.md", result.stderr)

    def test_cli_rejects_missing_root(self):
        result = self.cli(self.root / "missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot access scan root", result.stderr)

    def test_cli_help_succeeds(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Directory to scan", result.stdout)

    def test_cli_rejects_unknown_arguments(self):
        result = self.cli("--unknown-option")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_repository_passes_the_workflow_command(self):
        result = subprocess.run(
            [sys.executable, ".github/scripts/content_guard.py", "."],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("check passed successfully", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
