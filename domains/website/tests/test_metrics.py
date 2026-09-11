"""Metric modules: code metrics on a small site, judge metric in fake mode,
loader + failure isolation."""
import types

import pytest

from night_forge_mini.backends import FakeBackend

from domain_pack import metrics as metrics_mod
from domain_pack.site import Site

GOOD = ('<!DOCTYPE html><html><head><title>Good</title>'
        '<meta name="description" content="a page that has everything">'
        '</head><body><a href="other.html">ok</a>'
        '<a href="missing.html">broken</a>'
        '<link rel="stylesheet" href="/style.css">'
        '<a href="https://example.com/">external</a>'
        '<a href="#top">anchor</a></body></html>')
BARE = '<!DOCTYPE html><html><head><title>Bare</title></head><body>no meta</body></html>'


@pytest.fixture
def fake_model():
  return FakeBackend()


@pytest.fixture
def site( tmp_path ):
  s = Site(tmp_path / 'site')
  s.create_page('index.html', {'content': GOOD})
  s.create_page('other.html', {'content': BARE})
  s.create_page('style.css', {'content': 'body { color: #eee; }'})
  return s


def test_code_metrics( site, fake_model ):
  mods = metrics_mod.load(['pages', 'broken_links', 'seo_basics'])
  metric, errors = metrics_mod.measure_all(mods, site, model=fake_model, goal='g')
  assert errors == []
  assert metric == {'pages': 2,           # css is a file, not a page
                    'broken_links': 1,    # only missing.html; /style.css + external + anchor ok
                    'seo_basics': 1}      # only index.html has title AND meta description


def test_goal_coverage_is_deterministic_in_fake_mode( site, fake_model ):
  mods = metrics_mod.load(['goal_coverage'])
  metric, errors = metrics_mod.measure_all(mods, site, model=fake_model, goal='g')
  assert errors == []
  assert metric == {'goal_coverage': 5.0}


def test_keys_union_matches_config_order():
  mods = metrics_mod.load(['pages', 'goal_coverage'])
  assert metrics_mod.keys(mods) == ['pages', 'goal_coverage']


def test_unknown_metric_name_fails_fast_at_load():
  with pytest.raises(ModuleNotFoundError):
    metrics_mod.load(['no_such_metric'])


def test_broken_metric_is_skipped_not_fatal( site, fake_model ):
  boom = types.ModuleType('domain_pack.metrics.boom')     # a module, like a real drop-in
  boom.KEYS = ['boom']

  def _measure( site, *, model, goal ):
    raise RuntimeError('kaputt')

  boom.measure = _measure
  mods = metrics_mod.load(['pages']) + [boom]
  metric, errors = metrics_mod.measure_all(mods, site, model=fake_model, goal='g')
  assert metric == {'pages': 2}                        # pages still measured
  assert len(errors) == 1
  assert 'boom' in errors[0] and 'kaputt' in errors[0]
