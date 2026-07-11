"""web-source connector (pages mode): url#hash ids, watermark dedup, failure skip."""
import pytest

from domain_pack import connector as conn_mod
from domain_pack.connector import WebSourceConnector


def serve( monkeypatch, pages: dict ):
  def fake_read( url, **kwargs ):
    if url not in pages:
      raise ValueError(f'unreachable {url}')
    return pages[url]

  monkeypatch.setattr(conn_mod, '_read_url', fake_read)


def test_fetch_ids_are_url_hash_and_seen_filters( monkeypatch ):
  serve(monkeypatch, {'https://a.example': '# A page', 'https://b.example': '# B page'})
  conn = WebSourceConnector(['https://a.example', 'https://b.example'])

  first = conn.fetch(set())
  assert [s['source'] for s in first] == ['https://a.example', 'https://b.example']
  assert all(s['id'].startswith(f"{s['source']}#") for s in first)

  # unchanged pages -> already seen -> nothing new
  assert conn.fetch({s['id'] for s in first}) == []


def test_changed_page_reingests_with_new_id( monkeypatch ):
  conn = WebSourceConnector(['https://a.example'])
  serve(monkeypatch, {'https://a.example': 'version 1'})
  v1 = conn.fetch(set())
  serve(monkeypatch, {'https://a.example': 'version 2'})
  v2 = conn.fetch({s['id'] for s in v1})
  assert len(v2) == 1
  assert v2[0]['id'] != v1[0]['id']


def test_unreachable_url_is_skipped_not_fatal( monkeypatch ):
  serve(monkeypatch, {'https://ok.example': 'fine'})
  conn = WebSourceConnector(['https://down.example', 'https://ok.example'])
  out = conn.fetch(set())
  assert [s['source'] for s in out] == ['https://ok.example']


def test_snippet_text_is_bounded( monkeypatch ):
  serve(monkeypatch, {'https://a.example': 'x' * 10_000})
  conn = WebSourceConnector(['https://a.example'], snippet_max=100)
  out = conn.fetch(set())
  assert len(out[0]['text']) == 100
