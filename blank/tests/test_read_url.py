"""read_url built-in: page -> clean markdown via Jina Reader; free tier, optional key."""
import pytest

from night_forge_mini.tools import registry, read_url as ru


@pytest.fixture(autouse=True)
def no_key( monkeypatch ):
  monkeypatch.delenv('JINA_API_KEY', raising=False)


def capture_fetch( monkeypatch ):
  calls = []

  def fake_fetch( url, *, timeout=30.0, headers=None ):
    calls.append({'url': url, 'headers': headers or {}})
    return '# Page title\n\nclean markdown'

  monkeypatch.setattr(ru, '_fetch', fake_fetch)
  return calls


def test_prepends_jina_reader( monkeypatch ):
  calls = capture_fetch(monkeypatch)
  out = ru.read_url('https://example.com/page?a=1')
  assert calls[0]['url'] == 'https://r.jina.ai/https://example.com/page?a=1'
  assert 'Authorization' not in calls[0]['headers']   # free tier: no key, no header
  assert 'clean markdown' in out


def test_optional_key_becomes_bearer_header( monkeypatch ):
  monkeypatch.setenv('JINA_API_KEY', 'jk')
  calls = capture_fetch(monkeypatch)
  ru.read_url('https://example.com')
  assert calls[0]['headers']['Authorization'] == 'Bearer jk'


def test_rejects_non_http_targets():
  with pytest.raises(ValueError):
    ru.read_url('file:///etc/passwd')


def test_registered_and_available_without_key():
  tool = registry.get('read_url')
  assert tool is not None
  assert tool.available() is True                     # free tier -> always on
  assert tool.params['required'] == ['url']
