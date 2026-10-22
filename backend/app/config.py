from typing import Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://postgres:membernetwork@localhost:5432/member_network'
    supabase_url: str = ''
    supabase_publishable_key: str = ''
    supabase_secret_key: str = ''
    llm_provider: Literal['cursor', 'gemini', 'grok'] | None = None
    cursor_api_key: str = ''
    llm_model: str = ''
    cursor_model: str = 'gemini-3.7-flash-high'
    intro_llm_max_per_run: int = Field(default=10, ge=0, le=40)
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-3.8-flash'
    xai_api_key: str = ''
    grok_model: str = 'grok-3-mini'
    github_token: str = ''
    luma_event_ids: str = 'evt-Yz7RR89Zlv56tya'
    embedder: str = 'sentence-transformers'
    max_cf_weight: float = 0.7
    cf_k0: float = 8.0
    thread_silence_days: float = 3.0

    @field_validator('llm_provider', mode='before')
    @classmethod
    def empty_provider(cls, value):
        return value or None

    @model_validator(mode='after')
    def default_provider(self):
        if self.llm_provider is None:
            self.llm_provider = 'cursor' if self.cursor_api_key else 'gemini'
        return self


settings = Settings()
