from __future__ import annotations

import sys
from pathlib import Path


def _ensure_on_syspath(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


REPO_ROOT = Path(__file__).resolve().parents[1]
_ensure_on_syspath(REPO_ROOT)
_ensure_on_syspath(REPO_ROOT / "src")
