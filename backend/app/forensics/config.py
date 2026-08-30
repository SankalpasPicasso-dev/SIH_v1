"""Feature flags for optional, evidence-only forensic detectors."""
from __future__ import annotations

import os


def enabled(name: str, default: bool = True) -> bool:
    """Read FORENSICS_<NAME>_ENABLED without coupling policy to detectors."""
    value = os.getenv(f"FORENSICS_{name.upper()}_ENABLED")
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

