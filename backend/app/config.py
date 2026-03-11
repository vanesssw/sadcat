from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    api_id: int = 12345
    api_hash: str = "test_hash"
    tg_phone: str = "+1234567890"
    bot_username: str = "test_bot"

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    # App
    secret_key: str = "change_me"
    leaderboard_update_interval: int = 300  # seconds

    # Random.org
    random_org_api_key: str = ""

    # Yandex SmartCaptcha
    yandex_smartcaptcha_client_key: str = ""
    yandex_smartcaptcha_server_key: str = ""

    # Domain
    domain: str = "localhost"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
