"""fetch_binary built-in: HTTP(S) -> raw bytes; raises on oversize; never model-exposed."""
import urllib.request

import pytest

from night_forge_mini.tools import registry, fetch_binary as fb


class FakeResp:
  def __init__( self, body ):
    self.body = body

  def read( self, n=-1 ):
    return self.body if n < 0 else self.body[:n]

  def __enter__( self ):
    return self

  def __exit__( self, *args ):
    return False


def serve( monkeypatch, body ):
  monkeypatch.setattr(urllib.request, 'urlopen',
                      lambda req, timeout=None: FakeResp(body))


def test_returns_bytes_unmodified( monkeypatch ):
  png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
  serve(monkeypatch, png)
  assert fb.fetch_binary('https://example.com/logo.png') == png


def test_rejects_non_http_targets():
  with pytest.raises(ValueError):
    fb.fetch_binary('file:///etc/passwd')


def test_oversize_body_raises_instead_of_truncating( monkeypatch ):
  serve(monkeypatch, b'x' * 11)
  with pytest.raises(ValueError, match='max_bytes'):
    fb.fetch_binary('https://example.com/big.bin', max_bytes=10)


def test_body_at_cap_passes( monkeypatch ):
  serve(monkeypatch, b'x' * 10)
  assert fb.fetch_binary('https://example.com/ok.bin', max_bytes=10) == b'x' * 10


def test_registered_available_and_not_model_exposed():
  tool = registry.get('fetch_binary')
  assert tool is not None
  assert tool.available() is True     # stdlib-only, no key
  assert tool.params is None          # bytes result -> never handed to the model
