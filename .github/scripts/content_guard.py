"""Scan repository text files, failing closed on incomplete scans."""

import argparse
import os
from pathlib import Path
import sys

FORBIDDEN_TERMS = ("restricted-placeholder", "dummy-bad-content")
TEXT_EXTENSIONS = frozenset({".py", ".md", ".txt", ".yml", ".yaml"})
SCRIPT_PATH = Path(__file__).resolve()


def check_content(target_dir: str | Path = ".") -> int:
    """Return 0 for clean content, 1 for violations, or 2 for scan errors."""
    print("Initializing ASF Free Content Guard verification...")
    try:
        scan_root = Path(target_dir).resolve(strict=True)
        if not scan_root.is_dir():
            raise NotADirectoryError(f"Not a directory: {scan_root}")
    except OSError as error:
        print(f"Error: Cannot access scan root: {error}", file=sys.stderr)
        return 2

    scanned_files = 0
    violations = 0
    errors = 0

    def report_error(path: object, error: object) -> None:
        nonlocal errors
        errors += 1
        print(f"Error: Cannot scan {path}: {error}", file=sys.stderr)

    def report_walk_error(error: OSError) -> None:
        report_error(error.filename or scan_root, error)

    for directory, dirnames, filenames in os.walk(
        scan_root, topdown=True, onerror=report_walk_error, followlinks=False
    ):
        directory_path = Path(directory)
        kept_directories = []
        for name in sorted(dirnames):
            if name == ".git":
                continue
            path = directory_path / name
            try:
                if path.is_symlink():
                    raise OSError("Refusing to traverse a symbolic-link directory")
            except OSError as error:
                report_error(path.relative_to(scan_root), error)
            else:
                kept_directories.append(name)
        dirnames[:] = kept_directories

        for name in sorted(filenames):
            path = directory_path / name
            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            relative_path = path.relative_to(scan_root)
            try:
                if path.is_symlink():
                    raise OSError("Refusing to read a symbolic-link text file")
                if path.resolve(strict=True) == SCRIPT_PATH:
                    continue
                if not path.is_file():
                    raise OSError("Not a regular text file")
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                report_error(relative_path, error)
                continue

            scanned_files += 1
            for term in FORBIDDEN_TERMS:
                if term in content:
                    violations += 1
                    print(f"Violation: {relative_path}: prohibited term {term!r}")

    print(
        f"Scanned {scanned_files} text file(s); "
        f"{violations} prohibited term match(es); {errors} scan error(s)."
    )
    if errors:
        print("Content Guard check failed: Scan incomplete.", file=sys.stderr)
        return 2
    if violations:
        print("Content Guard check failed: Restricted terms detected.")
        return 1
    print("Content Guard check passed successfully!")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", default=".", help="Directory to scan (default: current directory)"
    )
    return check_content(parser.parse_args(argv).path)


if __name__ == "__main__":
    sys.exit(main())
