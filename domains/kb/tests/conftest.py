"""Make the blank core AND this domain's pack importable when pytest runs from anywhere.

The pack is loaded as `kb_domain_pack`, not `domain_pack`: the documented test command
collects both domains in ONE session, and the website tests import theirs as
`domain_pack` — whichever loaded first would silently stand in for the other."""
import importlib.util
import sys
from pathlib import Path

_domain = Path(__file__).parents[1]              # domains/kb
_repo = _domain.parents[1]                       # repo root

sys.path.insert(0, str(_repo / 'blank'))         # night_forge_mini

if 'kb_domain_pack' not in sys.modules:
  _pkg = _domain / 'domain_pack'
  _spec = importlib.util.spec_from_file_location('kb_domain_pack', _pkg / '__init__.py',
                                                 submodule_search_locations=[str(_pkg)])
  _mod = importlib.util.module_from_spec(_spec)
  sys.modules['kb_domain_pack'] = _mod
  _spec.loader.exec_module(_mod)
