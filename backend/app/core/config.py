from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auto WeChat Publisher"
    app_env: str = "local"
    log_level: str = "INFO"
    api_cors_origins: str = "http://localhost:5173"
    mysql_dsn: str = "mysql+pymysql://autopost:autopost@localhost:3306/autopost?charset=utf8mb4"
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model_name: str | None = None
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    wechat_auto_publish: bool = False
    
    # 文件上传限制
    max_upload_size_mb: int = 10
    allowed_image_extensions: str = ".jpg,.jpeg,.png,.gif,.webp"
    
    # HTTP 重试配置
    http_retry_attempts: int = 3
    http_retry_delay: float = 1.0

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]
    
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024
    
    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip().lower() for ext in self.allowed_image_extensions.split(",") if ext.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
