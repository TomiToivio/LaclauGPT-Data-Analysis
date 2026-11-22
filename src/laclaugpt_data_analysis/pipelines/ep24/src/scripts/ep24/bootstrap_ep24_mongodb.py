#!/usr/bin/env python3
"""Public entry point for EP24 MongoDB bootstrap."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ep24_settings import load_private_env

load_private_env()

from ep24_bootstrap import main

if __name__ == "__main__":
    raise SystemExit(main())
