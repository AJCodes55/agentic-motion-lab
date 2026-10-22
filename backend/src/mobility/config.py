from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Local service configuration; byte limits use decimal MB."""
    model_config = SettingsConfigDict(env_prefix='MOBILITY_', extra='ignore', populate_by_name=True)
    host: str = '127.0.0.1'
    port: int = 8000
    # Decimal MB; local development defaults approved for Phase 2.
    data_root: Path = Path(__file__).resolve().parents[2] / '.local-data'
    max_file_bytes: int = Field(default=25_000_000, gt=0)
    max_total_bytes: int = Field(default=50_000_000, gt=0)
    max_expanded_bytes: int = Field(default=200_000_000, gt=0)
    max_csv_members: int = Field(default=100, gt=0)
    body_read_timeout_seconds: float = Field(default=30, gt=0)
    openai_api_key: SecretStr | None = Field(default=None, validation_alias='OPENAI_API_KEY')
    openai_base_url: Literal['https://api.openai.com/v1', 'https://api.portkey.ai/v1'] = Field(
        default='https://api.openai.com/v1', validation_alias='OPENAI_BASE_URL')
    openai_model: str = Field(default='gpt-5-nano', min_length=1, validation_alias='OPENAI_MODEL')
    llm_timeout_seconds: float = Field(default=20, gt=0, le=120)
