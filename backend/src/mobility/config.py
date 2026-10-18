from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only configuration; no credentials required in Phase 1."""
    model_config = SettingsConfigDict(env_prefix='MOBILITY_', extra='ignore')
    host: str = '127.0.0.1'
    port: int = 8000
