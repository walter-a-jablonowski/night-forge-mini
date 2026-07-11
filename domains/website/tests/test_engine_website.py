"""End-to-end: the blank Engine running the website pack offline (--fake-llm),
with and without git-backed autonomy for the irreversible edit_content."""
import json
import subprocess

import pytest

from night_forge_mini.config import Config
from night_forge_mini.loop import Engine

import domain_pack
from domain_pack import connector as conn_mod

SEED = ('<!DOCTYPE html><html><head><title>New Site</title></head>'
        '<body><main><h1>New Site</h1></main></body></html>')


def make_cfg( tmp_path, git_enabled: bool ) -> Config:
  raw = {
    'provider': 'fake',
    'providers': {'fake': {'base_url': '', 'api_key_env': '', 'model': 'fake'}},
    'paths': {'log': 'data/log.jsonl', 'site': 'data/site'},
    'site_goal': 'a simple healthy nutrition site',
    'connector': {'mode': 'pages', 'pages': ['https://source.example/']},
    'metrics': ['pages', 'broken_links', 'seo_basics', 'goal_coverage'],
    'allow_list': ['create_page', 'edit_content'],
    'recent_runs': 5,
  }
  if git_enabled:
    raw['git'] = {'enabled': True, 'repo_dir': 'data/site',
                  'granularity': 'per_action', 'remote': '', 'branch': 'main'}
  return Config(raw=raw, root=tmp_path)


def make_engine( tmp_path, monkeypatch, *, git_enabled: bool, page_text: str ) -> Engine:
  site_dir = tmp_path / 'data' / 'site'
  site_dir.mkdir(parents=True, exist_ok=True)
  (site_dir / 'index.html').write_text(SEED, encoding='utf-8')
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: page_text)
  cfg = make_cfg(tmp_path, git_enabled)
  if git_enabled:
    git(site_dir, 'init')
    git(site_dir, 'config', 'user.email', 'test@test')
    git(site_dir, 'config', 'user.name', 'test')
    git(site_dir, 'add', '-A')
    git(site_dir, 'commit', '-m', 'seed')
  return Engine(cfg, domain_pack.build_pack(cfg), fake_llm=True)


def git( cwd, *args ):
  res = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True)
  assert res.returncode == 0, res.stderr
  return res.stdout


def test_run_creates_page_and_measures_metrics( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False,
                    page_text='Healthy Bowls\nput in a bowl, heat up, ready')
  res = eng.run_once()
  assert res['status'] == 'ok'
  assert res['captured'] == 1
  # fake analyze proposes create_page (reversible + allow-listed) -> auto-run even without git
  assert [r['action']['name'] for r in res['ran']] == ['create_page']
  assert res['pending'] == []
  assert (tmp_path / 'data/site/pages/healthy-bowls.html').is_file()
  assert res['metric']['pages'] == 1            # measured at analyze time, BEFORE acting
  assert res['metric']['goal_coverage'] == 5.0  # judge metric: deterministic in fake mode
  assert res['metric']['incoming_new'] == 1


def test_unchanged_source_is_noop( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='same text')
  assert eng.run_once()['status'] == 'ok'
  assert eng.run_once()['status'] == 'noop'     # url#hash unchanged -> watermark holds


def test_edit_holds_without_git_and_runs_on_approval( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='Healthy Bowls\nv1')
  eng.run_once()                                # creates pages/healthy-bowls.html
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: 'Healthy Bowls\nv2')
  res = eng.run_once()
  # page exists now -> fake analyze proposes edit_content; no git -> irreversible -> HELD
  assert res['ran'] == []
  assert [a['name'] for a in res['pending']] == ['edit_content']
  page = tmp_path / 'data/site/pages/healthy-bowls.html'
  assert 'v1' in page.read_text(encoding='utf-8')

  approved = eng.approve(res['pending'][0]['action_id'])
  assert approved['res']['result']['status'] == 'ok'
  assert 'v2' in page.read_text(encoding='utf-8')


def test_edit_autoruns_with_git_and_is_committed( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=True, page_text='Healthy Bowls\nv1')
  r1 = eng.run_once()
  assert [r['action']['name'] for r in r1['ran']] == ['create_page']
  assert [g['status'] for g in r1['git']] == ['ok']     # per-action commit

  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: 'Healthy Bowls\nv2')
  r2 = eng.run_once()
  # git-backed autonomy: irreversible edit_content auto-runs because git supplies the undo
  assert [r['action']['name'] for r in r2['ran']] == ['edit_content']
  assert r2['pending'] == []
  page = tmp_path / 'data/site/pages/healthy-bowls.html'
  assert 'v2' in page.read_text(encoding='utf-8')

  log = git(tmp_path / 'data/site', 'log', '--format=%s')
  assert 'edit_content' in log and 'create_page' in log and 'seed' in log


def test_stamped_base_is_in_the_proposal_log( tmp_path, monkeypatch ):
  eng = make_engine(tmp_path, monkeypatch, git_enabled=False, page_text='Healthy Bowls\nv1')
  eng.run_once()
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: 'Healthy Bowls\nv2')
  res = eng.run_once()
  # stale-edit guard: the held edit carries the fingerprint of what it was based on
  assert res['pending'][0]['payload'].get('base')
  records = [json.loads(line) for line in
             (tmp_path / 'data/log.jsonl').read_text(encoding='utf-8').splitlines()]
  assert any(r['type'] == 'proposal' for r in records)
