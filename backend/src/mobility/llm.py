"""Bounded, typed calls to the OpenAI Chat Completions API."""

import json
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings


T = TypeVar('T', bound=BaseModel)
_SCHEMA_KEYS = frozenset({'$defs', '$ref', 'type', 'properties', 'required', 'additionalProperties',
                          'items', 'anyOf', 'enum', 'const', 'description', 'title'})


class ProviderSchemaError(ValueError):
    """Model output failed the requested strict schema."""

    def __init__(self) -> None:
        super().__init__('LLM output did not match the requested schema')


class ProviderUnavailable(RuntimeError):
    """Safe public failure; never includes upstream body, prompt, or credentials."""

    def __init__(self) -> None:
        super().__init__('LLM provider unavailable')


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    value: T
    usage: LLMUsage


class LLMProvider(Protocol):
    def request(self, schema: type[T], system: str, payload: dict[str, object]) -> LLMResult[T]: ...


def _strict_schema(source: object) -> object:
    """Keep the OpenAI strict subset; Pydantic enforces discarded constraints locally."""
    if isinstance(source, list):
        return [_strict_schema(item) for item in source]
    if not isinstance(source, dict):
        return source
    result = {
        key: ({name: _strict_schema(value) for name, value in field_map.items()}
              if key in ('properties', '$defs') else _strict_schema(field_map))
        for key, field_map in source.items() if key in _SCHEMA_KEYS
    }
    if result.get('type') == 'object':
        result['additionalProperties'] = False
        result['required'] = list(result.get('properties', {}))
    return result


def _usage(data: object) -> LLMUsage:
    if not isinstance(data, dict):
        raise ProviderUnavailable()
    values = [data.get('prompt_tokens'), data.get('completion_tokens'), data.get('total_tokens')]
    if any(type(value) is not int or value < 0 for value in values):
        raise ProviderUnavailable()
    if values[0] + values[1] != values[2]:
        raise ProviderUnavailable()
    return LLMUsage(*values)


class OpenAIProvider:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport

    def request(self, schema: type[T], system: str, payload: dict[str, object]) -> LLMResult[T]:
        key = self._settings.openai_api_key
        if key is None or not key.get_secret_value().strip():
            raise ProviderUnavailable()
        body = {
            'model': self._settings.openai_model,
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps(payload, separators=(',', ':'), sort_keys=True)},
            ],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': schema.__name__[:64], 'strict': True,
                'schema': _strict_schema(schema.model_json_schema()),
            }},
            'max_completion_tokens': 2048,
            'reasoning_effort': 'minimal',
            'stream': False,
        }
        try:
            with httpx.Client(transport=self._transport, timeout=self._settings.llm_timeout_seconds) as client:
                response = client.post(f'{self._settings.openai_base_url}/chat/completions', json=body, headers={
                    'Authorization': f'Bearer {key.get_secret_value()}',
                })
            response.raise_for_status()
            data = response.json()
            choice = data['choices'][0]
            if choice['finish_reason'] != 'stop' or choice['message'].get('refusal'):
                raise ProviderUnavailable()
            content = choice['message']['content']
            if not isinstance(content, str):
                raise ProviderUnavailable()
            try:
                value = schema.model_validate_json(content)
            except ValidationError:
                raise ProviderSchemaError() from None
            return LLMResult(value=value, usage=_usage(data.get('usage')))
        except ProviderSchemaError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise ProviderUnavailable() from None
