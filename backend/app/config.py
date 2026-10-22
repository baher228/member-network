from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://postgres:membernetwork@localhost:5432/member_network'
    supabase_url: str = ''
    supabase_publishable_key: str = ''
    supabase_secret_key: str = ''
    xai_api_key: str = ''
    grok_model: str = 'grok-3-mini'
    github_token: str = ''
    luma_event_ids: str = 'evt-Yz7RR89Zlv56tya'
    embedder: str = 'sentence-transformers'
    max_cf_weight: float = 0.7
    cf_k0: float = 8.0
    thread_silence_days: float = 3.0


settings = Settings()
