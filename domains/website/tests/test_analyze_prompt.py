"""The analyze prompt must not let the model mistake an ACTION for a callable TOOL.

Regression for the first real-model run (2026-09-04, run-7eb9729b): the prompt rendered the
five actions in call syntax next to the real tool descriptions, so the model spent 6 of its
8 tool steps calling `create_page`, `add_asset` and `web_search` as tools, created no pages,
downloaded no images, and shipped an index.html linking to two pages that never existed.
"""
from domain_pack import analyze as analyze_mod
from domain_pack.actions import ACTIONS
from domain_pack.site import Site


class RecordingModel:
  """Captures the system prompt handed to run_tools; proposes nothing."""

  fake = False

  def __init__( self ):
    self.system = ''
    self.user = ''
    self.offered = []

  def run_tools( self, system, user, *, tools, schema, max_steps ):
    self.system, self.user, self.offered = system, user, [t.name for t in tools]
    return {'finding': 'recorded', 'actions': []}

  def complete_json( self, system, user, schema=None ):
    self.system, self.user = system, user
    return {'finding': 'recorded', 'actions': []}

  def label( self ):
    return 'recording'


def run_analyze( tmp_path, *, tool_steps=8 ) -> RecordingModel:
  site_dir = tmp_path / 'site'
  site_dir.mkdir(parents=True, exist_ok=True)
  (site_dir / 'index.html').write_text('<html><head><title>x</title></head></html>',
                                       encoding='utf-8')
  model = RecordingModel()
  analyze_mod.analyze(model, site=Site(site_dir), goal='a nutrition site', constraints='',
                      snippets=[{'id': 's1', 'source': 'https://src.example/', 'text': 'greens'}],
                      history={}, metric_mods=[], tool_steps=tool_steps)
  return model


def tools_section( system: str ) -> str:
  """The part of the prompt that tells the model what it may CALL."""
  start = system.index('TOOLS YOU CAN CALL NOW')
  return system[start:system.index('ACTIONS ARE NOT TOOLS', start)]


def test_no_action_is_named_as_a_callable_tool( tmp_path ):
  section = tools_section(run_analyze(tmp_path).system)
  for name in ACTIONS:
    assert name not in section, f'action {name} offered as a callable tool'


def test_actions_are_rendered_as_json_not_as_calls( tmp_path ):
  system = run_analyze(tmp_path).system
  for name in ACTIONS:
    assert f'{name}(' not in system, f'{name} rendered in call syntax'
  assert '"name": "create_page"' in system              # the shape they must be returned in


def test_tools_line_matches_the_tools_actually_offered( tmp_path ):
  model = run_analyze(tmp_path)
  section = tools_section(model.system)
  assert model.offered                                  # read_page at minimum
  for name in model.offered:
    assert name in section


def test_pending_reason_is_rendered_when_there_is_no_new_input( tmp_path ):
  site_dir = tmp_path / 'site'
  site_dir.mkdir(parents=True, exist_ok=True)
  (site_dir / 'index.html').write_text('<html><head><title>x</title></head></html>',
                                       encoding='utf-8')
  model = RecordingModel()
  analyze_mod.analyze(model, site=Site(site_dir), goal='g', constraints='', snippets=[],
                      history={'pending': '2 broken internal link(s)'}, metric_mods=[])
  assert '2 broken internal link(s)' in model.user     # the model is told WHY it ran
  assert '(none this pass)' in model.user              # ...and that there is no new input
