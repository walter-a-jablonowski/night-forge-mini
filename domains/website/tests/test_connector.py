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


# --- boilerplate: capture must deliver CONTENT, not a menu -------------------

WIKI_SHAPED = """Title: Spider plant

URL Source: https://en.wikipedia.org/wiki/Spider_plant

Markdown Content:
[Jump to content](https://en.wikipedia.org/wiki/Spider_plant#bodyContent)

- [x] Main menu

Main menu

move to sidebar hide

 Navigation

*   [Main page](https://en.wikipedia.org/wiki/Main_Page "Visit the main page")
*   [Contents](https://en.wikipedia.org/wiki/Wikipedia:Contents "Guides to browsing")
*   [Current events](https://en.wikipedia.org/wiki/Portal:Current_events "Current events")
*   [Random article](https://en.wikipedia.org/wiki/Special:Random "Load a random article")

Chlorophytum comosum, usually called spider plant, is a species of evergreen perennial
flowering plant. It is easy to grow indoors and tolerates a wide range of conditions.
"""


def test_capture_skips_leading_navigation( monkeypatch ):
  """Measured live: Wikipedia's article text began at char 6,140 while snippet_max was
  4,000, so three captured pages delivered nothing but menus — and the watermark then
  marked them seen, so the content could never be re-ingested."""
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: WIKI_SHAPED)
  snip = WebSourceConnector(['https://x.example/'], snippet_max=200).fetch(set())[0]

  assert snip['text'].startswith('Chlorophytum comosum')      # content, not the menu
  assert 'Main menu' not in snip['text']
  assert 'Random article' not in snip['text']


def test_a_page_without_navigation_is_untouched( monkeypatch ):
  plain = ('Title: X\n\nMarkdown Content:\n'
           'This page is prose from its very first line and carries no menu in front of '
           'it at all, so the stripper has nothing to drop here.')
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: plain)
  snip = WebSourceConnector(['https://x.example/'], snippet_max=500).fetch(set())[0]
  assert snip['text'].startswith('This page is prose')


def test_a_short_opening_line_falls_back_to_the_whole_page( monkeypatch ):
  """The prose test needs a line long enough to be unmistakable (60 chars of non-link
  text). Below that the page is returned unchanged — conservative on purpose: a missed
  strip costs some snippet budget, a wrong strip costs the content itself."""
  terse = 'Title: X\n\nMarkdown Content:\nShort opening line.\nAnother short one.'
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: terse)
  snip = WebSourceConnector(['https://x.example/'], snippet_max=500).fetch(set())[0]
  assert 'Short opening line.' in snip['text']


def test_an_all_links_page_still_captures_something( monkeypatch ):
  """Never make it worse: if nothing looks like prose, keep what there is rather than
  handing the model an empty snippet."""
  nav_only = 'Title: Y\n\nMarkdown Content:\n*   [a](http://a)\n*   [b](http://b)\n'
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: nav_only)
  snip = WebSourceConnector(['https://y.example/'], snippet_max=500).fetch(set())[0]
  assert snip['text'].strip()


INFOBOX_SHAPED = """Title: Monstera deliciosa

Markdown Content:
*   [Main page](https://en.wikipedia.org/wiki/Main_Page "Visit the main page")

| [![Image 1](https://thumb.wikimedia.org/a/b/Monstera.jpg)](https://upload.wikimedia.org/Monstera.jpg) |
| --- | --- |
| Scientific classification | Kingdom: Plantae | Family: Araceae |

Monstera deliciosa, the Swiss cheese plant, is a species of flowering plant native to
tropical forests of southern Mexico, popular as a houseplant for its large split leaves.
"""


def test_capture_skips_image_tables_too( monkeypatch ):
  """The first strip only got past the MENU: on a real Wikipedia article it stopped at the
  image infobox and removed 218 of 36,848 chars. A table of images is furniture as much as
  a menu is."""
  monkeypatch.setattr(conn_mod, '_read_url', lambda url, **kw: INFOBOX_SHAPED)
  snip = WebSourceConnector(['https://x.example/'], snippet_max=300).fetch(set())[0]

  assert snip['text'].startswith('Monstera deliciosa, the Swiss cheese plant')
  assert 'Image 1' not in snip['text']
  assert 'Scientific classification' not in snip['text']
