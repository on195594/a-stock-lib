"""Recorded prompt fragment hashes.

Run `python3 scripts/render_prompts.py --update-manifest` after intentional
canonical fragment edits to refresh these values.
"""
from __future__ import annotations

FRAGMENT_HASHES: dict[str, str] = {
    "cycle_stage.md": "2922e6560d0976e241e493721ef2eed6a4e058bb017a85821795687b885256e1",
    "dual_track_rating.md": "0a027fdd1c15ac0d907a893aeea3dea2817076a16d478910220675425e294c8f",
    "industry_routing.md": "9d563ee138eb015b8fc0f4ea085b898c7ed556d911a669d13fc0f7b95e9852ab",
    "subjective_evidence.md": "63f70904a773659ace7d94dbe205cc6bfcd838069b26b385a59a599a32a20e9d",
}
