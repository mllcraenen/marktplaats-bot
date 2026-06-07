from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_token: str = ""
    telegram_chat_id: str = "5157436441"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_email: str = "marijn@craenen.tech"

    database_url: str = "sqlite+aiosqlite:///./data/marktplaats.db"

    app_env: str = "production"
    log_level: str = "INFO"

    default_postcode: str = "3027CM"
    default_radius_km: int = 25


settings = Settings()
