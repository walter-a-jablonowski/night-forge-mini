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


def make_engine( tmp_path, analyze, items, allow_list=('safe_act',), actions=None ):
  pack = Pack(domain='test', goal='g', connector=StubConnector(items),
              actions=actions or make_actions(), analyze=analyze)
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
  assert seen_history == {'findings': [], 'metrics': [], 'rejections': [], 'failures': []}
  held = r['pending'][0]
  eng.reject(held['action_id'])

  items.append({'id': 's2', 'text': 'two', 'source': 'x'})
  eng.run_once()
  assert seen_history['findings'] == ['first finding']
  assert seen_history['metrics'] == [{'m': 1}]
  assert seen_history['rejections'] == [{'name': 'danger_act', 'target': 'held-1',
                                         'rationale': 'because'}]
  assert seen_history['failures'] == [{'name': 'safe_act', 'target': 't1', 'detail': 'boom'}]


def test_tool_trace_is_logged_as_spans_under_the_analysis( tmp_path ):
  items = [{'id': 's1', 'text': 'one', 'source': 'x'}]

  def analyze(model, *, goal, snippets, history):
    model._tool_trace.append({'tool': 'read_entry', 'args': {'id': 'vpn'}, 'status': 'ok',
                              'chars': 42, 'start': 't0', 'end': 't1'})
    return {'finding': 'f', 'metric': {}, 'actions': []}

  eng = make_engine(tmp_path, analyze, items)
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
