"""Config storage for tenant environment configurations."""

import json
from pathlib import Path
from typing import Optional

from api.models import EnvironmentConfig
from api.settings import settings


class ConfigStore:
    """Store tenant environment configurations as JSON files."""

    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir or settings.config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, tenant_slug: str, environment: str) -> Path:
        return self.config_dir / f"{tenant_slug}-{environment}.json"

    def save(self, tenant_slug: str, environment: str, config: EnvironmentConfig) -> None:
        """Save environment configuration."""
        path = self._get_path(tenant_slug, environment)
        data = {
            "tenant_slug": tenant_slug,
            "environment": environment,
            "config": config.model_dump(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, tenant_slug: str, environment: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration."""
        path = self._get_path(tenant_slug, environment)
        if not path.exists():
            return None

        with open(path) as f:
            data = json.load(f)
            return EnvironmentConfig(**data.get("config", {}))

    def delete(self, tenant_slug: str, environment: str) -> bool:
        """Delete environment configuration."""
        path = self._get_path(tenant_slug, environment)
        if not path.exists():
            return False
        path.unlink()
        return True


# Global instance
config_store = ConfigStore()
