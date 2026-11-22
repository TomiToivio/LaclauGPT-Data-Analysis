"""File checksums for staging verification and reproducible analysis runs."""

import hashlib
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    """Return the hexadecimal SHA-256 of the file's raw bytes."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
