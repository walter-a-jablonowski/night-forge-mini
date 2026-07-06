"""REPL robustness: a failing command must print an error, not kill the session."""
from night_forge_mini.cli import _repl

from test_engine import make_engine


def test_repl_survives_command_exception( tmp_path, monkeypatch, capsys ):
  items = [{'id': 's1', 'text': 'x', 'source': 'y'}]

  def analyze(model, **kw):
    raise RuntimeError('LLM down')

  eng = make_engine(tmp_path, analyze, items)
  inputs = iter(['run', 'inbox', 'quit'])
  monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))

  assert _repl(eng) == 0
  out = capsys.readouterr().out
  assert 'RuntimeError' in out and 'LLM down' in out
  assert 'inbox empty' in out                         # session continued after the error
