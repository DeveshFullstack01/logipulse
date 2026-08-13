from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://logipulse:logipulse@localhost:5432/logipulse"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:19092"
    kafka_topic: str = "shipment-events"
    ws_channel: str = "ws:broadcast"

    simulator_tick_seconds: float = 2.0
    delay_alert_threshold_hours: float = 4.0
    stale_shipment_minutes: int = 30


settings = Settings()
