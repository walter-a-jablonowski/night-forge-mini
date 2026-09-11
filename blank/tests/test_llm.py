"""HttpBackend: native structured output with graceful fallback per provider."""
from types import SimpleNamespace

import pytest

from night_forge_mini.backends import LLMError
from night_forge_mini.backends.base import _extract_json
from night_forge_mini.backends.http import HttpBackend
from night_forge_mini.pack import proposal_schema

PROVIDER = {'name': 'p', 'model': 'm', 'base_url': 'http://localhost', 'api_key_env': 'K'}
REPLY = '{"finding": "f", "actions": []}'


class ParamRejected(Exception):
  status_code = 400


def make_wrapper( handler ):
  """HttpBackend with a stub client; handler(kwargs) -> content str or raises."""
  calls = []

  def create( **kw ):
    calls.append(kw)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=handler(kw)))])

  w = HttpBackend(PROVIDER)
  w._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
  return w, calls


def test_schema_is_sent_as_response_format():
  w, calls = make_wrapper(lambda kw: REPLY)
  schema = proposal_schema(['add_entry'])
  out = w.complete_json('sys', 'usr', schema=schema)
  assert out == {'finding': 'f', 'actions': []}
  rf = calls[0]['response_format']
  assert rf['type'] == 'json_schema'
  assert rf['json_schema']['schema'] is schema


def test_no_schema_sends_no_response_format():
  w, calls = make_wrapper(lambda kw: REPLY)
  w.complete_json('sys', 'usr')
  assert 'response_format' not in calls[0]


def test_provider_rejection_falls_back_and_is_remembered():
  def handler( kw ):
    if 'response_format' in kw:
      raise ParamRejected('unknown parameter')
    return REPLY

  w, calls = make_wrapper(handler)
  schema = proposal_schema(['add_entry'])
  assert w.complete_json('sys', 'usr', schema=schema) == {'finding': 'f', 'actions': []}
  assert len(calls) == 2 and 'response_format' not in calls[1]

  # rejection is remembered: the next call skips the schema attempt entirely
  w.complete_json('sys', 'usr', schema=schema)
  assert len(calls) == 3 and 'response_format' not in calls[2]


def test_non_param_errors_still_raise():
  class ServerErr(Exception):
    status_code = 500

  def handler( kw ):
    raise ServerErr('boom')

  w, calls = make_wrapper(handler)
  with pytest.raises(ServerErr):
    w.complete_json('sys', 'usr', schema=proposal_schema(['a']))
  assert len(calls) == 1                              # no blind retry on server errors


def test_proposal_schema_shape():
  s = proposal_schema(['add_entry', 'edit_entry'])
  item = s['properties']['actions']['items']
  assert item['properties']['name']['enum'] == ['add_entry', 'edit_entry']
  assert set(item['required']) == {'name', 'target', 'rationale', 'payload'}
  payload = {'type': 'object', 'properties': {'body': {'type': 'string'}}}
  assert proposal_schema(['a'], payload_schema=payload)['properties']['actions']['items']['properties']['payload'] is payload


def test_extract_json_still_tolerates_fenced_prose():
  assert _extract_json('sure!\n```json\n{"a": 1}\n```') == {'a': 1}


def test_client_timeout_and_retries_are_bounded_and_configurable():
  c = HttpBackend(PROVIDER)._ensure_client()
  assert c.timeout == 120.0 and c.max_retries == 2    # sane defaults, not the SDK's 600s

  tuned = dict(PROVIDER, timeout=5, max_retries=0)
  c = HttpBackend(tuned)._ensure_client()
  assert c.timeout == 5.0 and c.max_retries == 0


def test_extract_json_turns_any_parse_failure_into_a_retryable_llm_error():
  """A model once answered the goal_coverage judge with a 64714-digit number (run-a257a9c6).
  json.loads raises a plain ValueError there, not JSONDecodeError, so it escaped both the
  tolerant extraction and the JSON retry and surfaced as a crashed metric."""
  huge = '{"score": ' + '9' * 5000 + ', "reason": "x"}'
  with pytest.raises(LLMError):
    _extract_json(huge)


def test_extract_json_requires_an_object():
  # the declared return type is a dict; a bare array/string must be retryable, not a
  # surprise type that blows up in the caller
  with pytest.raises(LLMError):
    _extract_json('[1, 2, 3]')


# --- a transient upstream 400 is not a parameter rejection -----------------

class UpstreamError(Exception):
  """What OpenRouter returns when the upstream it routed to fails: a 400 that says
  nothing about our parameters. Seen 3 times live, always naming a provider."""
  status_code = 400

  def __init__( self ):
    super().__init__("Error code: 400 - {'error': {'message': 'Provider returned error', "
                     "'code': 400, 'metadata': {'provider_name': 'AtlasCloud'}}}")


def test_a_transient_upstream_400_does_not_disable_structured_output():
  """The bug this covers: any 400 was read as "this provider cannot take response_format"
  and structured output was switched off for the wrapper's whole life. A flaky upstream
  would silently degrade every later call in the run."""
  seen = {'n': 0}

  def handler( kw ):
    seen['n'] += 1
    if seen['n'] == 1:
      raise UpstreamError()          # first attempt, schema sent, upstream is unhappy
    return REPLY

  w, calls = make_wrapper(handler)
  schema = proposal_schema(['add_entry'])
  assert w.complete_json('sys', 'usr', schema=schema) == {'finding': 'f', 'actions': []}

  # the request is resent AS IS — OpenRouter routes per request, so the same call usually
  # lands on a healthy provider. The schema survives; falling back to plain would have
  # given up structured output over someone else's outage.
  assert len(calls) == 2 and 'response_format' in calls[1]

  # ...and nothing was learned about the parameter, so later calls still send the schema
  w.complete_json('sys', 'usr', schema=schema)
  assert 'response_format' in calls[2]


def test_a_400_that_names_the_parameter_is_still_remembered():
  class NamedRejection(Exception):
    status_code = 400
    def __init__( self ):
      super().__init__("400: response_format is not supported by this model")

  def handler( kw ):
    if 'response_format' in kw:
      raise NamedRejection()
    return REPLY

  w, calls = make_wrapper(handler)
  schema = proposal_schema(['add_entry'])
  w.complete_json('sys', 'usr', schema=schema)
  w.complete_json('sys', 'usr', schema=schema)
  assert all('response_format' not in c for c in calls[1:])      # learned, as before
