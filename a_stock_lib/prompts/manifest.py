"""Recorded prompt fragment hashes.

Run `python3 scripts/render_prompts.py --update-manifest` after intentional
canonical fragment edits to refresh these values.
"""
from __future__ import annotations

FRAGMENT_HASHES: dict[str, str] = {
    "cycle_stage.md": "2922e6560d0976e241e493721ef2eed6a4e058bb017a85821795687b885256e1",
    "dual_track_rating.md": "0001494af10e3c17e7592735da3459c268e3e4f1c71271066f9cca43616e1dd4",
    "industry_routing.md": "7956c9a347c23d6c35512873080e3fb28396582271b9cf968c7fc843f764e827",
    "subjective_evidence.md": "c3f052ba968ab24c407c7b68fc137ab8eee96b31ec20732b8d91b7cd6f698891",
}
