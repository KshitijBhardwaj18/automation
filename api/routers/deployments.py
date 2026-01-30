"""Deployment endpoints."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.config_store import config_store
from api.database import db
from api.models import (
    Deployment,
    DeploymentResponse,
    DeploymentStatus,
    DeployRequest,
    DestroyRequest,
)
from api.services.deployment import deployment_service

router = APIRouter(prefix="/api/v1/tenants", tags=["Deployments"])


@router.post("/{slug}/environments/{environment}/deploy", response_model=DeploymentResponse)
async def deploy(
    slug: str,
    environment: str,
    request: DeployRequest,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Deploy infrastructure."""
    stack_name = f"{slug}-{environment}"

    tenant = db.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    config = config_store.get(slug, environment)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Config for {slug}/{environment} not found. Save config first.",
        )

    existing = db.get_deployment(slug, environment)
    if existing:
        if existing.status == DeploymentStatus.IN_PROGRESS:
            raise HTTPException(status_code=409, detail="Deployment already in progress")
        if existing.status == DeploymentStatus.SUCCEEDED:
            raise HTTPException(
                status_code=409,
                detail="Deployment exists. Destroy first to redeploy.",
            )

    try:
        db.create_deployment(
            tenant_id=tenant.id,
            tenant_slug=slug,
            environment=environment,
            aws_region=tenant.aws_region,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    background_tasks.add_task(deployment_service.deploy, tenant, environment, config)

    return DeploymentResponse(
        tenant_slug=slug,
        environment=environment,
        stack_name=stack_name,
        status=DeploymentStatus.PENDING,
        message="Deployment initiated",
    )


@router.get("/{slug}/environments/{environment}/status", response_model=Deployment)
async def get_status(slug: str, environment: str) -> Deployment:
    """Get deployment status."""
    deployment = await deployment_service.sync_status(slug, environment)
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment for {slug}/{environment} not found",
        )
    return deployment


@router.delete("/{slug}/environments/{environment}")
async def destroy(
    slug: str,
    environment: str,
    request: DestroyRequest,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Destroy infrastructure."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Must set confirm=true")

    deployment = db.get_deployment(slug, environment)
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment for {slug}/{environment} not found",
        )

    if deployment.status == DeploymentStatus.DESTROYING:
        raise HTTPException(status_code=409, detail="Destruction already in progress")

    background_tasks.add_task(deployment_service.destroy, slug, environment)

    return DeploymentResponse(
        tenant_slug=slug,
        environment=environment,
        stack_name=deployment.stack_name,
        status=DeploymentStatus.DESTROYING,
        message="Destruction initiated",
    )
