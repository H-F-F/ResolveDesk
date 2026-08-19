"""Backend application package."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


_ROOT_DIR = Path(__file__).resolve().parents[2]
_VENDOR_DIR = _ROOT_DIR / ".vendor"


def _should_use_vendor_packages() -> bool:
    force_vendor = os.getenv("APP_USE_VENDOR_PACKAGES")
    if force_vendor is not None:
        return force_vendor == "1"
    return importlib.util.find_spec("fastapi") is None


if _VENDOR_DIR.exists() and _should_use_vendor_packages():
    vendor_path = str(_VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
