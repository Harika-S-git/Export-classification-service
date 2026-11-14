from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    redis_url: str
    verifier_url: str
    provider_url: str
    provider_mode: str = 'stub'
    provider_model: str = ''
    provider_api_key: str = ''
    otel_exporter_otlp_endpoint: str = ''
    data_dir: str = '/data'
    corpus_dir: str = 'corpus'
    prompt_version: str = 'v2'
    call_timeout: float = 5
    max_retries: int = 2
    max_steps: int = 20
    max_tool_calls: int = 14
    run_timeout: int = 45
    cache_enabled: bool = True
    cache_ttl: int = 3600
    rate_limit: int = 60
    rate_window: int = 60
    stub_delay: float = .75
    stub_fault: str = 'none'
    enable_faults: bool = False
    token_input_price: float = 0
    token_output_price: float = 0
    policy_snapshot_confirmed: bool = False
    quality_sample_every: int = 5

@lru_cache
def settings(): return Settings()
