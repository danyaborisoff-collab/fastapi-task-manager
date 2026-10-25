from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(pattern=r"^postgresql\+asyncpg://")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
