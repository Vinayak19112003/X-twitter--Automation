"""Pytest path bootstrap so tests import `config`, `agents`, and `xinfluencer_os`."""
from __future__ import annotations

import sys
from pathlib import Path

OS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = OS_ROOT.parent
# xinfluencer_os first so `import agents` wins over any similarly named folder.
for path in (str(REPO_ROOT), str(OS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
sys.path.insert(0, str(OS_ROOT))
