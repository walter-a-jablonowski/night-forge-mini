"""Store: watermark correctness (failed runs don't consume input) + cached reads
+ the predicted-vs-actual impact report."""
import json

from night_forge_mini.records import Record, INPUT, ANALYSIS, PROPOSAL, OUTCOME
from night_forge_mini.store import Store


def _input(run_id, connector, ids):
  return Record(run_id=run_id, domain='d', type=INPUT,
                payload={'connector': connector, 'snippet_ids': ids, 'snippets': []})


def _analysis(run_id, metric=None):
  return Record(run_id=run_id, domain='d', type=ANALYSIS,
                payload={'finding': 'f', 'metric': metric or {}})


def _proposal(run_id, actions):
  return Record(run_id=run_id, domain='d', type=PROPOSAL, payload={'actions': actions})


def _outcome(action_id, status='ok'):
  return Record(run_id='r', domain='d', type=OUTCOME, parent_id=action_id,
                payload={'action_id': action_id, 'name': 'a', 'status': status})


def test_watermark_ignores_runs_that_never_reached_analysis( tmp_path ):
  s = Store(tmp_path / 'log.jsonl')
  s.append(_input('run-1', 'c', ['a', 'b']))          # crashed before analyze
  assert s.seen_snippet_ids('c') == set()

  s.append(_input('run-2', 'c', ['a', 'b']))          # retry succeeded
  s.append(_analysis('run-2'))
  assert s.seen_snippet_ids('c') == {'a', 'b'}


def test_watermark_is_per_connector( tmp_path ):
  s = Store(tmp_path / 'log.jsonl')
  s.append(_input('run-1', 'c1', ['a']))
  s.append(_analysis('run-1'))
  assert s.seen_snippet_ids('c2') == set()


def test_append_through_cache_stays_consistent( tmp_path ):
  s = Store(tmp_path / 'log.jsonl')
  s.append(_input('run-1', 'c', ['a']))
  assert len(s.all()) == 1                            # first read loads + caches
  s.append(_analysis('run-1'))                        # append after a cached read
  assert len(s.all()) == 2


def test_external_append_is_picked_up( tmp_path ):
  path = tmp_path / 'log.jsonl'
  s = Store(path)
  s.append(_input('run-1', 'c', ['a']))
  assert len(s.all()) == 1

  # another process appends directly to the file
  ext = _analysis('run-1').to_dict()
  with path.open('a', encoding='utf-8') as f:
    f.write(json.dumps(ext) + '\n')
  assert len(s.all()) == 2
  assert s.seen_snippet_ids('c') == {'a'}


def test_impact_report_compares_predicted_with_measured_delta( tmp_path ):
  s = Store(tmp_path / 'log.jsonl')
  s.append(_analysis('run-1', {'entries': 3, 'stale': 1}))
  s.append(_proposal('run-1', [
    {'action_id': 'a1', 'name': 'add', 'expected_impact': {'entries': 1}},
    {'action_id': 'a2', 'name': 'add', 'expected_impact': {'entries': 5}},   # failed -> excluded
    {'action_id': 'a3', 'name': 'add', 'expected_impact': {'stale': -1}},    # pending -> excluded
  ]))
  s.append(_outcome('a1', 'ok'))
  s.append(_outcome('a2', 'error'))
  s.append(_analysis('run-2', {'entries': 4, 'stale': 1}))

  rep = s.impact_report(5)
  assert rep == [{'run_id': 'run-1', 'predicted': {'entries': 1}, 'actual': {'entries': 1}}]


def test_impact_report_skips_runs_without_predictions( tmp_path ):
  s = Store(tmp_path / 'log.jsonl')
  s.append(_analysis('run-1', {'entries': 3}))
  s.append(_proposal('run-1', [{'action_id': 'a1', 'name': 'add'}]))  # pack never opted in
  s.append(_outcome('a1', 'ok'))
  s.append(_analysis('run-2', {'entries': 4}))
  assert s.impact_report(5) == []
  assert Store(tmp_path / 'empty.jsonl').impact_report(5) == []


def test_torn_tail_is_skipped_and_next_append_survives( tmp_path ):
  path = tmp_path / 'log.jsonl'
  s = Store(path)
  s.append(_input('run-1', 'c', ['a']))
  with path.open('a', encoding='utf-8') as f:
    f.write('{"torn": ')                              # crash mid-write, no newline
  s.append(_analysis('run-1'))
  recs = s.all()
  assert [r.type for r in recs] == [INPUT, ANALYSIS]
