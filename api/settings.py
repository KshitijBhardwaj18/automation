"""Application settings loaded from environment variables or .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    These are loaded from environment variables or a .env file.
    Create a .env file in the project root with your settings.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Pulumi settings
    pulumi_access_token: str = ""
    pulumi_org: str = ""
    pulumi_project: str = "byoc-platform"

    # Git settings
    git_repo_url: str = ""
    git_repo_branch: str = "main"
    git_repo_dir: str = "."  # Subdirectory containing Pulumi.yaml
    github_token: str = ""  # For private repos (optional)

    # AWS credentials (for Pulumi Deployments)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance - loaded once at startup
settings = get_settings()
