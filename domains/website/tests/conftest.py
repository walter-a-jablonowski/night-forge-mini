"""Make the blank core AND this domain's `domain_pack` importable when pytest runs
from anywhere — no merged installation needed for the pack tests."""
import sys
from pathlib import Path

_domain = Path(__file__).parents[1]              # domains/website
_repo = _domain.parents[1]                       # repo root

sys.path.insert(0, str(_repo / 'blank'))         # night_forge_mini
sys.path.insert(0, str(_domain))                 # domain_pack
