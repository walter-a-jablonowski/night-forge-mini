"""Store: watermark correctness (failed runs don't consume input) + cached reads."""
import json

from night_forge_mini.records import Record, INPUT, ANALYSIS
from night_forge_mini.store import Store


def _input(run_id, connector, ids):
  return Record(run_id=run_id, domain='d', type=INPUT,
                payload={'connector': connector, 'snippet_ids': ids, 'snippets': []})


def _analysis(run_id):
  return Record(run_id=run_id, domain='d', type=ANALYSIS,
                payload={'finding': 'f', 'metric': {}})


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


def test_torn_tail_is_skipped_and_next_append_survives( tmp_path ):
  path = tmp_path / 'log.jsonl'
  s = Store(path)
  s.append(_input('run-1', 'c', ['a']))
  with path.open('a', encoding='utf-8') as f:
    f.write('{"torn": ')                              # crash mid-write, no newline
  s.append(_analysis('run-1'))
  recs = s.all()
  assert [r.type for r in recs] == [INPUT, ANALYSIS]
