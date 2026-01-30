"""Config endpoints."""

from fastapi import APIRouter, HTTPException

from api.config_store import config_store
from api.database import db
from api.models import ConfigResponse, EnvironmentConfig

router = APIRouter(prefix="/api/v1/tenants", tags=["Config"])


@router.post("/{slug}/environments/{environment}/config", response_model=ConfigResponse)
async def save_config(
    slug: str,
    environment: str,
    config: EnvironmentConfig,
) -> ConfigResponse:
    """Save environment configuration."""
    if not db.get_tenant_by_slug(slug):
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    config_store.save(slug, environment, config)

    return ConfigResponse(
        tenant_slug=slug,
        environment=environment,
        message="Configuration saved",
        config=config,
    )


@router.get("/{slug}/environments/{environment}/config", response_model=ConfigResponse)
async def get_config(slug: str, environment: str) -> ConfigResponse:
    """Get environment configuration."""
    if not db.get_tenant_by_slug(slug):
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    config = config_store.get(slug, environment)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Config for {slug}/{environment} not found",
        )

    return ConfigResponse(
        tenant_slug=slug,
        environment=environment,
        message="Configuration retrieved",
        config=config,
    )


@router.delete("/{slug}/environments/{environment}/config", response_model=ConfigResponse)
async def delete_config(slug: str, environment: str) -> ConfigResponse:
    """Delete environment configuration."""
    if not config_store.delete(slug, environment):
        raise HTTPException(
            status_code=404,
            detail=f"Config for {slug}/{environment} not found",
        )

    return ConfigResponse(
        tenant_slug=slug,
        environment=environment,
        message="Configuration deleted",
    )
