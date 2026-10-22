from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://postgres:membernetwork@localhost:5432/member_network'
    supabase_url: str = ''
    supabase_publishable_key: str = ''
    supabase_secret_key: str = ''
    llm_provider: Literal['gemini', 'grok'] = 'gemini'
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


settings = Settings()
