"""Prompt fragment hashing helpers."""
from __future__ import annotations

import hashlib
from pathlib import Path


FRAGMENT_FILENAMES = (
    "cycle_stage.md",
    "dual_track_rating.md",
    "industry_routing.md",
    "subjective_evidence.md",
)


def compute_fragment_hashes(fragments_dir: Path) -> dict[str, str]:
    """Return sha256 hex digests for canonical prompt fragments on disk."""
    hashes: dict[str, str] = {}
    for filename in FRAGMENT_FILENAMES:
        content = (fragments_dir / filename).read_bytes()
        hashes[filename] = hashlib.sha256(content).hexdigest()
    return hashes
