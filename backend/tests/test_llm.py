import json

import httpx
import pytest
from pydantic import Field

from mobility.config import Settings
from mobility.contracts import Contract
from mobility.llm import OpenAIProvider, ProviderUnavailable, ProviderSchemaError


class Answer(Contract):
    choice: str = Field(min_length=1)
    count: int = Field(ge=0)


def configured():
    return Settings(openai_api_key='openai-secret')


def completion(content):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': content}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 4, 'total_tokens': 16}}


def test_missing_credentials_fails_closed():
    provider = OpenAIProvider(Settings(openai_api_key=None))
    with pytest.raises(ProviderUnavailable, match='provider unavailable'):
        provider.request(Answer, 'Select', {'total': 3})


def test_strict_schema_request_and_typed_response():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion('{"choice":"x","count":3}'))

    provider = OpenAIProvider(configured(), transport=httpx.MockTransport(handle))
    result = provider.request(Answer, 'Select', {'total': 3})
    assert result.value == Answer(choice='x', count=3)
    assert result.usage.total_tokens == 16
    request = requests[0]
    assert str(request.url) == 'https://api.openai.com/v1/chat/completions'
    assert request.headers['authorization'] == 'Bearer openai-secret'
    assert 'x-portkey-api-key' not in request.headers
    assert 'x-portkey-provider' not in request.headers
    body = json.loads(request.content)
    assert body['model'] == 'gpt-5-nano'
    assert body['max_completion_tokens'] == 2048
    assert body['reasoning_effort'] == 'minimal'
    assert body['messages'][1]['content'] == '{"total":3}'
    schema = body['response_format']['json_schema']
    assert schema['strict'] is True
    assert schema['schema']['additionalProperties'] is False
    assert schema['schema']['required'] == ['choice', 'count']
    assert 'minimum' not in schema['schema']['properties']['count']


@pytest.mark.parametrize('response,expected_error', [
    (httpx.Response(500, text='openai-secret'), ProviderUnavailable),
    (httpx.Response(200, text='not json'), ProviderUnavailable),
    (httpx.Response(200, json=completion('{"choice":"x","count":-1}')), ProviderSchemaError),
    (httpx.Response(200, json=completion('{"choice":')), ProviderSchemaError),
    (httpx.Response(200, json={'choices': [], 'usage': {}}), ProviderUnavailable),
])
def test_invalid_response_redacts_provider_content(response, expected_error):
    provider = OpenAIProvider(configured(), transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(expected_error) as error:
        provider.request(Answer, 'Select', {'total': 3})
    assert 'openai-secret' not in str(error.value)
    assert 'choice' not in str(error.value)


def test_network_error_redacted():
    def handle(request):
        raise httpx.ConnectError('openai-secret', request=request)

    provider = OpenAIProvider(configured(), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderUnavailable) as error:
        provider.request(Answer, 'Select', {'total': 3})
    assert 'openai-secret' not in str(error.value)


def test_timeout_uses_configured_bound_and_safe_error(monkeypatch):
    seen = []
    original = httpx.Client

    def client(*args, **kwargs):
        seen.append(kwargs['timeout'])
        return original(*args, **kwargs)

    def handle(request):
        raise httpx.ReadTimeout('openai-secret', request=request)

    monkeypatch.setattr(httpx, 'Client', client)
    provider = OpenAIProvider(Settings(openai_api_key='openai-secret', llm_timeout_seconds=7),
                               transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderUnavailable) as error:
        provider.request(Answer, 'Select', {})
    assert seen == [7]
    assert 'openai-secret' not in str(error.value)


def test_standard_openai_api_key_environment(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'env-secret')
    assert Settings().openai_api_key.get_secret_value() == 'env-secret'


def test_university_gateway_and_model_are_configurable(monkeypatch):
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://api.portkey.ai/v1')
    monkeypatch.setenv('OPENAI_MODEL', '@30875-fall26-openai/gpt-5-nano')
    settings = Settings(openai_api_key='university-secret')
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion('{"choice":"x","count":3}'))

    result = OpenAIProvider(settings, transport=httpx.MockTransport(handle)).request(Answer, 'Select', {})
    assert result.value.count == 3
    request = requests[0]
    assert str(request.url) == 'https://api.portkey.ai/v1/chat/completions'
    assert request.headers['authorization'] == 'Bearer university-secret'
    assert 'x-portkey-provider' not in request.headers
    assert json.loads(request.content)['model'] == '@30875-fall26-openai/gpt-5-nano'


def test_unapproved_model_gateway_is_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(openai_base_url='https://example.test/v1')

def test_blank_key_fails_closed():
    provider = OpenAIProvider(Settings(openai_api_key=' '))
    with pytest.raises(ProviderUnavailable):
        provider.request(Answer, 'Select', {})
