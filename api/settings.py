"""Application settings loaded from environment variables or .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Pulumi settings
    pulumi_access_token: str = ""
    pulumi_org: str = ""
    pulumi_project: str = "byoc-platform"

    # Git settings
    git_repo_url: str = ""
    git_repo_branch: str = "main"
    git_repo_dir: str = "."
    github_token: str = ""

    # AWS credentials (for Pulumi Deployments)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # Config storage
    config_dir: str = "./configs"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
