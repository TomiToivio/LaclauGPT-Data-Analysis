# Privacy and configuration policy

This is a **public code repository**. Treat every committed byte as publishable.

## Never commit

- research datasets, raw captures, transcripts, media, exports or derived row-level data
- participant/user identifiers, API responses containing personal data, or private annotations
- `.env` files, access tokens, passwords, cookies, session data, SSH/private keys or cloud credentials
- MongoDB/Redis/S3 URLs containing credentials
- CSC Allas credentials, project-local machine paths or private cluster configuration
- private codebooks, source lists, unpublished project notes or restricted corpora unless explicitly cleared for publication

The repository ignores common data/config formats defensively, but `.gitignore` is not a security boundary. Check staged changes before every push.

## Configuration rule

Committed files may contain **schema and examples only**. Runtime configuration belongs in environment variables or untracked local files. `.env.example` contains variable names and safe placeholders only.

Local operation is the default:

- records: CSV or SQLite
- artifacts: local filesystem
- cache: in-memory

Distributed operation is opt-in:

- records: MongoDB
- cache/coordination: Redis
- object storage: S3-compatible storage such as CSC Allas

Secrets must be supplied through the environment, a secret manager, or deployment tooling. They must never be embedded in Python, notebooks, YAML, TOML, Markdown, tests, fixtures or GitHub Actions workflow files.

## Before publishing a change

Run `git status`, inspect `git diff --cached`, and verify that no data/config/secrets are staged. If a secret was ever committed, deleting the file is not enough: rotate/revoke the secret and remove it from Git history where appropriate.

## Tests and fixtures

Tests must use synthetic data generated in the test itself or obviously fake fixtures. Never copy real research rows into `tests/` to make a regression test convenient.
