from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auto WeChat Publisher"
    app_env: str = "local"
    api_cors_origins: str = "http://localhost:5173"
    mysql_dsn: str = "mysql+pymysql://autopost:autopost@localhost:3306/autopost?charset=utf8mb4"
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model_name: str | None = None
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    wechat_auto_publish: bool = False

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
