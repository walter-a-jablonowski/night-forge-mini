"""Metric targets: run while the goal is unmet, stop when it is met — or when it stopped
moving (tasks/backlog/run-when-metric-below-target.md)."""
import pytest

from night_forge_mini.config import Config
from night_forge_mini.loop import Engine
from night_forge_mini.pack import Action, Pack
from night_forge_mini.targets import Targets


def targets( raw, patience=3 ):
  return Targets.from_config(Config(raw={'metric_targets': raw, 'convergence_runs': patience},
                                    root='.'))


def runs( *values, key='score', chance=True ):
  return [{'metric': {key: v} if v is not None else {}, 'had_chance': chance} for v in values]


# --- the verdict -------------------------------------------------------------

def test_no_targets_changes_nothing():
  assert targets({}).check(runs(1, 1, 1, 1)).state == 'none'


def test_a_met_target_stops_with_goal_reached():
  v = targets({'score': 8}).check(runs(3, 9))
  assert v.state == 'met' and v.reason.startswith('goal reached') and 'score=9' in v.reason


def test_an_unmet_target_is_a_reason_to_run():
  v = targets({'score': 8}).check(runs(3, 5))
  assert v.state == 'unmet' and 'score=5' in v.reason and '8' in v.reason


def test_at_most_targets_count_down():
  assert targets({'broken': {'max': 0}}).check(runs(0, key='broken')).state == 'met'
  assert targets({'broken': {'max': 0}}).check(runs(2, key='broken')).state == 'unmet'


def test_a_metric_never_measured_is_not_met():
  """A judge that never worked (no key) must not let the loop claim the goal blind."""
  v = targets({'score': 8}, patience=3).check(runs(None, None))
  assert v.state == 'unmet' and 'not measured' in v.reason


def test_targets_read_the_last_measured_value():
  """One failed judge call (quota, outage) must not freeze or mislead the loop."""
  assert targets({'score': 8}).check(runs(9, None)).state == 'met'
  v = targets({'score': 8}).check(runs(5, None))
  assert v.state == 'unmet' and 'score=5' in v.reason


def test_missing_measurements_are_not_a_plateau():
  """Regression, live 2026-10-10: 'stopped improving' fired while the site grew from 3 to
  5 pages — the judge had hit its daily quota in two of three passes, and a missing value
  was counted as no movement."""
  v = targets({'score': 9.5}, patience=3).check(runs(None, None, 9.0, None))
  assert v.state == 'unmet'


def test_a_metric_that_cannot_be_measured_stops_the_loop_after_n_blind_runs():
  """Otherwise a broken judge would keep a no-input loop running on a goal it cannot see."""
  v = targets({'score': 8}, patience=3).check(runs(5, None, None, None))
  assert v.state == 'blind' and v.reason.startswith('cannot measure: score')
  assert targets({'score': 8}, patience=3).check(runs(5, None, None)).state == 'unmet'


def test_convergence_compares_real_measurements_n_runs_apart():
  # 5 measured, three chance-runs later 5 again, unmeasured runs in between
  hist = runs(5, None, 5, 5)
  assert targets({'score': 8}, patience=3).check(hist).state == 'converged'


def test_n_flat_runs_stop_with_stopped_improving():
  v = targets({'score': 8}, patience=3).check(runs(5, 5, 5, 5))
  assert v.state == 'converged' and v.reason.startswith('stopped improving')


def test_one_noisy_low_score_is_not_a_plateau():
  """Regression, live 2026-10-11: the judge scored 10.0 then 9.0 after a page was added,
  and comparing only the latest value with one N runs back (9.0 vs 9.0) stopped the loop."""
  assert targets({'score': 11}, patience=3).check(runs(9, 10, 10, 9)).state == 'unmet'


def test_n_runs_without_a_new_best_are_a_plateau():
  assert targets({'score': 11}, patience=3).check(runs(9, 10, 10, 9, 10)).state == 'converged'


def test_one_lucky_high_score_does_not_keep_the_loop_alive():
  assert targets({'score': 11}, patience=3).check(runs(9, 10, 9, 9, 9)).state == 'converged'


def test_at_most_targets_take_the_lowest_value_as_best():
  hist = runs(5, 2, 3, 4, 3, key='broken')
  assert targets({'broken': {'max': 0}}, patience=3).check(hist).state == 'converged'
  hist = runs(5, 4, 3, 2, key='broken')
  assert targets({'broken': {'max': 0}}, patience=3).check(hist).state == 'unmet'


def test_fewer_than_n_flat_runs_are_not_yet_convergence():
  assert targets({'score': 8}, patience=3).check(runs(5, 5, 5)).state == 'unmet'


def test_movement_toward_the_target_keeps_it_running():
  assert targets({'score': 8}, patience=3).check(runs(4, 4, 4, 5)).state == 'unmet'


def test_reaching_the_target_wins_over_a_plateau():
  """A finished artifact plateaus at its ceiling; it must say 'goal reached'."""
  assert targets({'score': 8}, patience=2).check(runs(9, 9, 9, 9)).state == 'met'


def test_growth_beyond_a_met_target_does_not_hide_a_stalled_one():
  """seo_basics keeps rising as pages are added; that is not progress on goal_coverage."""
  hist = [{'metric': {'cov': 5, 'seo': s}, 'had_chance': True} for s in (4, 6, 8, 10)]
  v = targets({'cov': 8, 'seo': 4}, patience=3).check(hist)
  assert v.state == 'converged' and 'cov=5' in v.reason and 'seo' not in v.reason


def test_runs_that_had_no_chance_are_not_evidence_of_convergence():
  """All actions failed or held: nothing changed, so the flat metric proves nothing."""
  hist = runs(5, 5, 5, 5, chance=False)
  assert targets({'score': 8}, patience=3).check(hist).state == 'unmet'


@pytest.mark.parametrize('bad', ['high', {'min': 'x'}, {'min': 1, 'max': 2}, {'avg': 3}, True])
def test_a_malformed_target_is_a_clear_config_error( bad ):
  with pytest.raises(ValueError, match='metric_targets.score'):
    targets({'score': bad})


# --- in the loop -------------------------------------------------------------

class Inbox:
  name = 'stub'

  def __init__( self ):
    self.items = []

  def fetch( self, seen_ids ):
    return [dict(s) for s in self.items if s['id'] not in seen_ids]


def make_engine( tmp_path, scores, actions_per_run=1, **cfg_extra ):
  """An engine whose metric follows `scores`, one value per analyze."""
  inbox, calls = Inbox(), {'n': 0}

  def analyze( model, *, goal, snippets, history ):
    calls['history'] = history
    score = scores[min(calls['n'], len(scores) - 1)]
    calls['n'] += 1
    acts = [{'name': 'improve', 'target': 't', 'rationale': 'r', 'payload': {}}] * actions_per_run
    return {'finding': f'score {score}', 'metric': {'score': score}, 'actions': acts}

  ok = Action(name='improve', risk_level='low', reversible=True,
              run=lambda t, p: {'status': 'ok', 'detail': 'done'})
  raw = {'provider': 'p', 'providers': {'p': {'model': 'm', 'base_url': 'x', 'api_key_env': 'K'}},
         'paths': {'log': 'data/log.jsonl'}, 'allow_list': ['improve'], 'recent_runs': 5}
  raw.update(cfg_extra)
  pack = Pack(domain='t', goal='g', connector=inbox, actions={'improve': ok}, analyze=analyze)
  return Engine(Config(raw=raw, root=tmp_path), pack, fake_llm=True), inbox, calls


def test_without_targets_no_input_is_still_a_noop( tmp_path ):
  eng, inbox, _ = make_engine(tmp_path, [3])
  inbox.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  eng.run_once()
  assert eng.run_once() == {'status': 'noop', 'reason': 'no new snippets'}


def test_the_loop_runs_below_target_and_stops_when_it_is_reached( tmp_path ):
  eng, inbox, calls = make_engine(tmp_path, [3, 6, 9], metric_targets={'score': 8})
  inbox.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  assert eng.run_once()['captured'] == 1                  # input-driven, score 3

  r = eng.run_once()                                      # no input, 3 < 8 -> runs
  assert r['status'] == 'ok' and r['captured'] == 0
  assert 'below target' in calls['history']['pending']    # analyze is told WHY
  eng.run_once()                                          # recorded 6 < 8 -> runs, measures 9

  r = eng.run_once()
  assert r['status'] == 'noop' and r['stop'] == 'met' and 'goal reached' in r['reason']


def test_the_loop_stops_when_the_metric_stops_moving( tmp_path ):
  eng, inbox, _ = make_engine(tmp_path, [4, 5, 5, 5, 5], metric_targets={'score': 8},
                              convergence_runs=3)
  inbox.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  states = [eng.run_once() for _ in range(7)]
  assert [s['status'] for s in states[:5]] == ['ok'] * 5
  assert states[5]['stop'] == 'converged' and 'stopped improving' in states[5]['reason']
  assert states[6]['stop'] == 'converged'                 # and it stays stopped


def test_new_input_still_runs_after_the_goal_is_reached( tmp_path ):
  """The targets gate the no-input path only: processing what the connector brings is
  the connector's contract."""
  eng, inbox, _ = make_engine(tmp_path, [9], metric_targets={'score': 8})
  inbox.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  eng.run_once()
  assert eng.run_once()['stop'] == 'met'
  inbox.items.append({'id': 's2', 'text': 'y', 'source': 'x'})
  assert eng.run_once()['captured'] == 1


def test_a_metric_run_that_changed_nothing_does_not_spin( tmp_path ):
  """Anti-spin guards the metric trigger too: the pass proposed nothing, so repeating it
  on the same reason would only burn tokens."""
  eng, inbox, _ = make_engine(tmp_path, [3], actions_per_run=0, metric_targets={'score': 8})
  inbox.items.append({'id': 's1', 'text': 'x', 'source': 'x'})
  eng.run_once()                                          # captured input = progress
  assert eng.run_once()['status'] == 'ok'                 # below target, runs, proposes nothing
  r = eng.run_once()
  assert r['status'] == 'noop' and 'made no progress' in r['reason']
