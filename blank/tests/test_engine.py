"""Engine: failed-run retry, history feedback into analyze, core-side sanitization."""
import pytest

from night_forge_mini.config import Config
from night_forge_mini.loop import Engine
from night_forge_mini.pack import Action, Pack
from night_forge_mini.records import ANALYSIS, PROPOSAL, TOOL_CALL


class StubConnector:
  name = 'stub'

  def __init__(self, items):
    self.items = items

  def fetch(self, seen_ids):
    return [dict(s) for s in self.items if s['id'] not in seen_ids]


def make_cfg( tmp_path, allow_list ):
  raw = {
    'provider': 'p',
    'providers': {'p': {'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}},
    'paths': {'log': 'data/log.jsonl'},
    'allow_list': allow_list,
    'recent_runs': 5,
  }
  return Config(raw=raw, root=tmp_path)


def make_actions( safe_run=None ):
  ok = lambda t, p: {'status': 'ok', 'detail': 'done'}
  return {
    'safe_act':   Action(name='safe_act', risk_level='low', reversible=True, run=safe_run or ok),
    'danger_act': Action(name='danger_act', risk_level='high', reversible=False, run=ok),
  }


def make_engine( tmp_path, analyze, items, allow_list=('safe_act',), actions=None,
                 pending_work=None ):
  pack = Pack(domain='test', goal='g', connector=StubConnector(items),
              actions=actions or make_actions(), analyze=analyze, pending_work=pending_work)
  return Engine(make_cfg(tmp_path, list(allow_list)), pack, fake_llm=True)


def proposal_action( analyzed_name, target='t1' ):
  return {'name': analyzed_name, 'target': target, 'rationale': 'because', 'payload': {}}


# --- fix 1: a failed analyze must not consume the input --------------------

def test_snippets_survive_an_analyze_crash( tmp_path ):
  items = [{'id': 's1', 'text': 'hello', 'source': 'x'}]
  calls = {'n': 0}

  def analyze(model, *, goal, snippets, history):
    calls['n'] += 1
    if calls['n'] == 1:
      raise RuntimeError('LLM down')
    return {'finding': 'ok', 'metric': {}, 'actions': []}

  eng = make_engine(tmp_path, analyze, items)
  with pytest.raises(RuntimeError):
    eng.run_once()

  r = eng.run_once()                                  # retry sees the same snippet again
  assert r['status'] == 'ok'
  assert r['captured'] == 1

  r = eng.run_once()                                  # now it is consumed
  assert r['status'] == 'noop'


# --- fix 2: decisions, outcomes and metrics feed the next run ---------------

def test_history_carries_findings_metrics_rejections_failures( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]
  seen_history = {}

  def analyze(model, *, goal, snippets, history):
    seen_history.clear()
    seen_history.update(history)
    return {'finding': 'first finding', 'metric': {'m': 1},
            'actions': [proposal_action('safe_act'), proposal_action('danger_act', 'held-1')]}

  fail = lambda t, p: {'status': 'error', 'detail': 'boom'}
  eng = make_engine(tmp_path, analyze, items, actions=make_actions(safe_run=fail))

  r = eng.run_once()
  assert seen_history == {'findings': [], 'metrics': [], 'rejections': [],
                          'failures': [], 'impact': []}
  held = r['pending'][0]
  eng.reject(held['action_id'])

  items.append({'id': 's2', 'text': 'two', 'source': 'x'})
  eng.run_once()
  assert seen_history['findings'] == ['first finding']
  assert seen_history['metrics'] == [{'m': 1}]
  assert seen_history['rejections'] == [{'name': 'danger_act', 'target': 'held-1',
                                         'rationale': 'because'}]
  assert seen_history['failures'] == [{'name': 'safe_act', 'target': 't1', 'detail': 'boom'}]


def test_impact_reaches_history_two_runs_later( tmp_path ):
  # metric is measured AT analyze, so run N's actual delta only exists once run N+1
  # analyzed -> the report about run 1 appears in run 3's history.
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]
  seen_history = {}
  metrics = iter([{'m': 1}, {'m': 3}, {'m': 3}])

  def analyze(model, *, goal, snippets, history):
    seen_history.clear()
    seen_history.update(history)
    a = proposal_action('safe_act')
    a['expected_impact'] = {'m': 2}
    return {'finding': 'f', 'metric': next(metrics), 'actions': [a]}

  eng = make_engine(tmp_path, analyze, items)
  eng.run_once()
  items.append({'id': 's2', 'text': 'two', 'source': 'x'})
  eng.run_once()
  assert seen_history['impact'] == []                 # run-1's delta not measurable yet
  items.append({'id': 's3', 'text': 'three', 'source': 'x'})
  r3 = eng.run_once()
  assert len(seen_history['impact']) == 1
  assert seen_history['impact'][0]['predicted'] == {'m': 2}
  assert seen_history['impact'][0]['actual'] == {'m': 2}


def test_expected_impact_is_sanitized_to_numbers( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]

  def analyze(model, *, goal, snippets, history):
    a1 = proposal_action('safe_act')
    a1['expected_impact'] = {'m': 1, 'junk': 'much', 'flag': True}
    a2 = proposal_action('safe_act', 't2')
    a2['expected_impact'] = 'lots'
    return {'finding': 'f', 'metric': {}, 'actions': [a1, a2]}

  eng = make_engine(tmp_path, analyze, items)
  r = eng.run_once()
  acts = [item['action'] for item in r['ran']]
  assert acts[0]['expected_impact'] == {'m': 1}       # numeric keys only, bools out
  assert 'expected_impact' not in acts[1]             # non-dict garbage removed


def test_tool_trace_is_logged_as_spans_under_the_analysis( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]

  span = {'tool': 'read_entry', 'args': {'id': 'vpn'}, 'status': 'ok',
          'chars': 42, 'start': 't0', 'end': 't1'}

  def analyze(model, *, goal, snippets, history):
    return {'finding': 'f', 'metric': {}, 'actions': []}

  eng = make_engine(tmp_path, analyze, items)
  # whatever the BACKEND reports as its trace is what the Engine must log — the contract
  # is `take_tool_trace()`, not any one backend's internals
  eng.model.take_tool_trace = lambda: [dict(span)]
  eng.run_once()
  analysis = eng.store.of_type(ANALYSIS)[0]
  spans = eng.store.of_type(TOOL_CALL)
  assert len(spans) == 1
  assert spans[0].parent_id == analysis.id
  assert spans[0].start_ts == 't0' and spans[0].end_ts == 't1'
  assert spans[0].payload == {'tool': 'read_entry', 'args': {'id': 'vpn'},
                              'status': 'ok', 'chars': 42}


# --- fix 3: the core sanitizes whatever analyze returns ---------------------

def test_malformed_actions_are_dropped_not_crashing( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]

  def analyze(model, *, goal, snippets, history):
    return {'finding': None, 'metric': 'garbage',
            'actions': ['junk', {'name': 'unknown_act'}, {'name': 'safe_act'}]}

  eng = make_engine(tmp_path, analyze, items)
  r = eng.run_once()
  assert r['status'] == 'ok'
  ran = [item['action'] for item in r['ran']]
  assert [a['name'] for a in ran] == ['safe_act']
  assert ran[0]['action_id'] and ran[0]['target'] == '' and ran[0]['payload'] == {}

  prop = eng.store.of_type(PROPOSAL)[0]
  assert len(prop.payload['dropped']) == 2


def test_non_list_actions_become_empty_proposal( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]
  analyze = lambda model, **kw: {'finding': 'f', 'actions': 'none'}
  eng = make_engine(tmp_path, analyze, items)
  r = eng.run_once()
  assert r['status'] == 'ok' and r['ran'] == [] and r['pending'] == []


def test_model_cannot_overrule_pack_gate_metadata( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]

  def analyze(model, *, goal, snippets, history):
    a = proposal_action('danger_act')
    a['reversible'] = True                            # model lies about reversibility
    a['risk_level'] = 'low'
    return {'finding': 'f', 'metric': {}, 'actions': [a]}

  # danger_act is allow-listed, but pack says irreversible -> must still be held
  eng = make_engine(tmp_path, analyze, items, allow_list=('safe_act', 'danger_act'))
  r = eng.run_once()
  assert r['ran'] == []
  assert r['pending'][0]['reversible'] is False
  assert r['pending'][0]['risk_level'] == 'high'


# --- pending work: a run when only the ARTIFACT has something outstanding --

def test_pending_work_runs_without_new_snippets( tmp_path ):
  """run-9d177565 left the site linking to two pages it never created, and every later
  pass was `no new snippets` — the artifact's own outstanding work triggered nothing."""
  seen = []

  def analyze(model, *, goal, snippets, history):
    seen.append((list(snippets), history.get('pending')))
    return {'finding': 'f', 'metric': {}, 'actions': [proposal_action('safe_act')]}

  items = [{'id': 's1', 'text': 'hello', 'source': 'x'}]
  eng = make_engine(tmp_path, analyze, items, pending_work=lambda: '2 broken link(s)')
  assert eng.run_once()['status'] == 'ok'             # first pass: real input

  r = eng.run_once()                                  # no new input, but work outstanding
  assert r['status'] == 'ok'
  assert r['captured'] == 0
  assert seen[1] == ([], '2 broken link(s)')          # analyze told WHY it was run


def test_no_pending_work_still_noops( tmp_path ):
  analyze = lambda model, **kw: {'finding': 'f', 'metric': {}, 'actions': []}
  items = [{'id': 's1', 'text': 'hello', 'source': 'x'}]

  eng = make_engine(tmp_path, analyze, items, pending_work=lambda: None)
  assert eng.run_once()['status'] == 'ok'
  assert eng.run_once()['status'] == 'noop'


def test_pending_work_does_not_spin_when_a_run_changes_nothing( tmp_path ):
  """A pack that keeps reporting the same unfinished work must not re-run forever: one
  pass that changes nothing is the stop signal."""
  proposals = [[proposal_action('safe_act')], [], []]

  def analyze(model, *, goal, snippets, history):
    return {'finding': 'f', 'metric': {}, 'actions': proposals.pop(0) if proposals else []}

  items = [{'id': 's1', 'text': 'hello', 'source': 'x'}]
  eng = make_engine(tmp_path, analyze, items, pending_work=lambda: 'still broken')

  assert eng.run_once()['status'] == 'ok'             # input + an action that ran
  assert eng.run_once()['status'] == 'ok'             # pending, previous run made progress
  r = eng.run_once()                                  # previous pending run did nothing
  assert r['status'] == 'noop'
  assert 'no progress' in r['reason']


# --- the backend seam ------------------------------------------------------

def test_fake_llm_selects_the_fake_backend_rather_than_a_mode( tmp_path ):
  """`--fake-llm` picks a backend; the http one has no special mode to get stuck in."""
  from night_forge_mini.backends import FakeBackend, HttpBackend

  analyze = lambda model, **kw: {'finding': 'f', 'metric': {}, 'actions': []}
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]

  eng = make_engine(tmp_path, analyze, items)
  assert isinstance(eng.model, FakeBackend) and eng.model.fake is True
  assert eng.model.label() == 'fake-llm'
  assert HttpBackend.fake is False


def test_unknown_backend_name_is_a_clear_config_error( tmp_path ):
  pack = Pack(domain='test', goal='g', connector=StubConnector([]),
              actions=make_actions(), analyze=lambda model, **kw: {})
  cfg = make_cfg(tmp_path, [])
  cfg.raw['backend'] = 'nope'
  with pytest.raises(ValueError) as e:
    Engine(cfg, pack)
  assert 'nope' in str(e.value) and 'http' in str(e.value)   # names what IS available


def test_fake_backend_refuses_to_answer_instead_of_inventing( tmp_path ):
  """A missed branch must fail loudly: a silent stub would turn it into a made-up answer."""
  from night_forge_mini.backends import FakeBackend, LLMError

  with pytest.raises(LLMError):
    FakeBackend().complete_json('sys', 'usr')
  with pytest.raises(LLMError):
    FakeBackend().run_tools('sys', 'usr', tools=[])
