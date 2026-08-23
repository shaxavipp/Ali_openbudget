from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_id: int
    channel_id: int
    payments_channel_id: int
    verifiers_channel_id: int
    database_url: str
    timezone: str = "Asia/Tashkent"
    verifier_tag: str = "shaxa"


settings = Settings()
