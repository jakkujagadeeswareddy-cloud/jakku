# ASF Free Content Guard

A dependency-free repository text scanner. This is a literal-term guard, not a
complete content-classification or license-compliance system.

## Run locally

Use Python 3.11 or later from the repository root:

```sh
python .github/scripts/content_guard.py .
python -m unittest discover -s tests -v
```

The optional scan path defaults to the current directory. The configured terms
are defined in the guard script; test fixtures use those definitions at runtime.

## Scan scope and exclusions

- Scan UTF-8 `.py`, `.md`, `.txt`, `.yml`, and `.yaml` files, including uppercase
  extensions and files under `.github` and other hidden directories.
- Prune directories whose exact name is `.git`, including nested Git metadata.
  Names merely containing that substring are not excluded.
- Exclude only the running guard script itself, because it defines the terms.
  Other scripts in the same directory are still checked.
- Ignore unsupported file extensions. Report and fail on unreadable or invalid
  UTF-8 text, directory traversal failures, nonregular text files, and symbolic
  links to selected text files or directories inside the scan root. Links are
  not followed outside the scan root.
- Report each matched term per file in deterministic traversal order, plus
  counts of successfully scanned files, matches, and scan errors.

Exit codes: **0** for a complete clean scan, **1** for prohibited content, and
**2** for an incomplete scan or invalid invocation. Scan errors take precedence
when both errors and violations occur; scanning continues to report other issues.

## Continuous integration

The workflow runs syntax checks, the regression suite, and the repository scan
on Python 3.11, 3.12, and 3.13. It covers pushes to `main`, `feature-branch`,
`fix/asf-free-content-guard`, and `feature/content-guard`, plus pull requests
against `main`. Actions receive read-only repository permissions; failures are
not suppressed. The existing workflow filename is retained to avoid changing
its identity unnecessarily.
