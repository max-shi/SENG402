"""
frame_config: shared per-frame parameter lookup.

The extended n=2000 frame (RULES.md) reuses the
same pipeline scripts as the original n=200 frame. Each frame records
its target sample size in frame_metadata.json
(`n_target_per_ecosystem`, written by sample_frame.py at draw time).
Scripts that re-role primaries/reserves must use the frame's own
target rather than a hardcoded 200, so they call load_n_target() with
the frame directory.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_N_TARGET = 200


def load_n_target(frame_dir: Path, default: int = DEFAULT_N_TARGET) -> int:
    """Return n_target_per_ecosystem from the frame's metadata, or
    `default` if the metadata file is missing or unreadable."""
    meta_path = Path(frame_dir) / "frame_metadata.json"
    if not meta_path.exists():
        return default
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return int(meta.get("n_target_per_ecosystem", default))
    except (ValueError, OSError):
        return default
