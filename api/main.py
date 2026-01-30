"""FastAPI application for BYOC Platform - Tenant-based architecture."""

import json
import secrets
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.config_store import config_store
from api.database import Database, TenantRecord, db
from api.models import (
    ConfigResponse,
    Deployment,
    DeploymentResponse,
    DeploymentStatus,
    DeployRequest,
    DestroyRequest,
    EnvironmentConfig,
    Tenant,
    TenantCreate,
    TenantResponse,
)
from api.pulumi_deployments import PulumiDeploymentsClient
from api.settings import settings

app = FastAPI(
    title="BYOC Platform API",
    description="Multi-tenant BYOC infrastructure deployment platform",
    version="2.0.0",
)


# =============================================================================
# HELPERS
# =============================================================================


def get_pulumi_client() -> PulumiDeploymentsClient:
    """Get Pulumi Deployments client."""
    return PulumiDeploymentsClient(
        organization=settings.pulumi_org,
        access_token=settings.pulumi_access_token,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        github_token=settings.github_token or None,
    )


async def run_deployment(
    tenant: TenantRecord,
    environment: str,
    config: EnvironmentConfig,
    database: Database,
) -> None:
    """Background task to run deployment."""
    stack_name = f"{tenant.slug}-{environment}"

    try:
        client = get_pulumi_client()

        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.IN_PROGRESS,
        )

        # Create stack if needed
        try:
            await client.create_stack(
                project_name=settings.pulumi_project,
                stack_name=stack_name,
            )
        except Exception:
            pass

        # Configure deployment
        await client.configure_deployment_settings(
            project_name=settings.pulumi_project,
            stack_name=stack_name,
            tenant_slug=tenant.slug,
            environment=environment,
            role_arn=tenant.role_arn,
            external_id=tenant.external_id,
            aws_region=tenant.aws_region,
            config=config,
            repo_url=settings.git_repo_url,
            repo_branch=settings.git_repo_branch,
            repo_dir=settings.git_repo_dir,
        )

        # Trigger deployment
        result = await client.trigger_deployment(
            project_name=settings.pulumi_project,
            stack_name=stack_name,
            operation="update",
        )

        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.IN_PROGRESS,
            pulumi_deployment_id=result.get("id", ""),
        )

    except Exception as e:
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.FAILED,
            error_message=str(e),
        )


async def run_destroy(tenant_slug: str, environment: str, database: Database) -> None:
    """Background task to destroy infrastructure."""
    stack_name = f"{tenant_slug}-{environment}"

    try:
        client = get_pulumi_client()

        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.DESTROYING,
        )

        result = await client.trigger_deployment(
            project_name=settings.pulumi_project,
            stack_name=stack_name,
            operation="destroy",
        )

        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.DESTROYING,
            pulumi_deployment_id=result.get("id", ""),
        )

    except Exception as e:
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.FAILED,
            error_message=str(e),
        )


# =============================================================================
# HEALTH
# =============================================================================


@app.get("/health")
async def health_check() -> dict:
    """Health check."""
    return {"status": "healthy"}


# =============================================================================
# TENANT ENDPOINTS
# =============================================================================


@app.post("/api/v1/tenants", response_model=TenantResponse)
async def create_tenant(request: TenantCreate) -> TenantResponse:
    """Create a new tenant.

    Generates external_id for IAM role assumption.
    Returns tenant with external_id (shown only once).
    """
    tenant_id = str(uuid.uuid4())
    external_id = secrets.token_urlsafe(32)
    role_arn = f"arn:aws:iam::{request.aws_account_id}:role/BYOCPlatformRole"

    try:
        record = db.create_tenant(
            id=tenant_id,
            slug=request.slug,
            name=request.name,
            aws_account_id=request.aws_account_id,
            aws_region=request.aws_region,
            role_arn=role_arn,
            external_id=external_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    tenant = Tenant(
        id=record.id,
        slug=record.slug,
        name=record.name,
        aws_account_id=record.aws_account_id,
        aws_region=record.aws_region,
        role_arn=record.role_arn,
        external_id=record.external_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

    return TenantResponse(
        tenant=tenant,
        message="Tenant created. Save the external_id - it won't be shown again.",
    )


@app.get("/api/v1/tenants", response_model=list[Tenant])
async def list_tenants() -> list[Tenant]:
    """List all tenants."""
    records = db.list_tenants()
    return [
        Tenant(
            id=r.id,
            slug=r.slug,
            name=r.name,
            aws_account_id=r.aws_account_id,
            aws_region=r.aws_region,
            role_arn=r.role_arn,
            external_id=r.external_id,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]


@app.get("/api/v1/tenants/{slug}", response_model=Tenant)
async def get_tenant(slug: str) -> Tenant:
    """Get tenant by slug."""
    record = db.get_tenant_by_slug(slug)
    if not record:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    return Tenant(
        id=record.id,
        slug=record.slug,
        name=record.name,
        aws_account_id=record.aws_account_id,
        aws_region=record.aws_region,
        role_arn=record.role_arn,
        external_id=record.external_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.delete("/api/v1/tenants/{slug}")
async def delete_tenant(slug: str) -> dict:
    """Delete tenant (must have no active deployments)."""
    deployments = db.list_deployments(tenant_slug=slug)
    active = [
        d for d in deployments
        if d.status not in [DeploymentStatus.DESTROYED, DeploymentStatus.FAILED]
    ]
    if active:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete tenant with active deployments. Destroy them first.",
        )

    deleted = db.delete_tenant(slug)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    return {"message": f"Tenant '{slug}' deleted"}


# =============================================================================
# CONFIG ENDPOINTS
# =============================================================================


@app.post(
    "/api/v1/tenants/{slug}/environments/{environment}/config",
    response_model=ConfigResponse,
)
async def save_config(
    slug: str,
    environment: str,
    config: EnvironmentConfig,
) -> ConfigResponse:
    """Save environment configuration for a tenant."""
    tenant = db.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    config_store.save(slug, environment, config)

    return ConfigResponse(
        tenant_slug=slug,
        environment=environment,
        message="Configuration saved",
        config=config,
    )


@app.get(
    "/api/v1/tenants/{slug}/environments/{environment}/config",
    response_model=ConfigResponse,
)
async def get_config(slug: str, environment: str) -> ConfigResponse:
    """Get environment configuration."""
    tenant = db.get_tenant_by_slug(slug)
    if not tenant:
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


@app.delete(
    "/api/v1/tenants/{slug}/environments/{environment}/config",
    response_model=ConfigResponse,
)
async def delete_config(slug: str, environment: str) -> ConfigResponse:
    """Delete environment configuration."""
    deleted = config_store.delete(slug, environment)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Config for {slug}/{environment} not found",
        )

    return ConfigResponse(
        tenant_slug=slug,
        environment=environment,
        message="Configuration deleted",
    )


# =============================================================================
# DEPLOYMENT ENDPOINTS
# =============================================================================


@app.post(
    "/api/v1/tenants/{slug}/environments/{environment}/deploy",
    response_model=DeploymentResponse,
)
async def deploy(
    slug: str,
    environment: str,
    request: DeployRequest,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Deploy infrastructure for a tenant environment."""
    stack_name = f"{slug}-{environment}"

    # Get tenant
    tenant = db.get_tenant_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    # Get config
    config = config_store.get(slug, environment)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Config for {slug}/{environment} not found. Save config first.",
        )

    # Check existing deployment
    existing = db.get_deployment(slug, environment)
    if existing:
        if existing.status == DeploymentStatus.IN_PROGRESS:
            raise HTTPException(status_code=409, detail="Deployment already in progress")
        if existing.status == DeploymentStatus.SUCCEEDED:
            raise HTTPException(
                status_code=409,
                detail="Deployment exists. Destroy first to redeploy.",
            )

    # Create deployment record
    try:
        db.create_deployment(
            tenant_id=tenant.id,
            tenant_slug=slug,
            environment=environment,
            aws_region=tenant.aws_region,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Run in background
    background_tasks.add_task(run_deployment, tenant, environment, config, db)

    return DeploymentResponse(
        tenant_slug=slug,
        environment=environment,
        stack_name=stack_name,
        status=DeploymentStatus.PENDING,
        message="Deployment initiated",
    )


@app.get(
    "/api/v1/tenants/{slug}/environments/{environment}/status",
    response_model=Deployment,
)
async def get_status(slug: str, environment: str) -> Deployment:
    """Get deployment status."""
    deployment = db.get_deployment(slug, environment)
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment for {slug}/{environment} not found",
        )

    # Check Pulumi for updates if in progress
    if deployment.status == DeploymentStatus.IN_PROGRESS and deployment.pulumi_deployment_id:
        try:
            client = get_pulumi_client()
            status = await client.get_deployment_status(
                project_name=settings.pulumi_project,
                stack_name=deployment.stack_name,
                deployment_id=deployment.pulumi_deployment_id,
            )

            pulumi_status = status.get("status", "")
            if pulumi_status == "succeeded":
                outputs = await client.get_stack_outputs(
                    project_name=settings.pulumi_project,
                    stack_name=deployment.stack_name,
                )
                db.update_deployment_status(
                    stack_name=deployment.stack_name,
                    status=DeploymentStatus.SUCCEEDED,
                    outputs=json.dumps(outputs),
                )
                deployment = db.get_deployment(slug, environment)
            elif pulumi_status == "failed":
                db.update_deployment_status(
                    stack_name=deployment.stack_name,
                    status=DeploymentStatus.FAILED,
                    error_message=status.get("message", "Deployment failed"),
                )
                deployment = db.get_deployment(slug, environment)
        except Exception:
            pass

    return Deployment(
        id=deployment.id,
        tenant_id=deployment.tenant_id,
        tenant_slug=deployment.tenant_slug,
        environment=deployment.environment,
        stack_name=deployment.stack_name,
        aws_region=deployment.aws_region,
        status=deployment.status,
        pulumi_deployment_id=deployment.pulumi_deployment_id,
        outputs=json.loads(deployment.outputs) if deployment.outputs else None,
        error_message=deployment.error_message,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
    )


@app.delete("/api/v1/tenants/{slug}/environments/{environment}")
async def destroy(
    slug: str,
    environment: str,
    request: DestroyRequest,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Destroy infrastructure for a tenant environment."""
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

    background_tasks.add_task(run_destroy, slug, environment, db)

    return DeploymentResponse(
        tenant_slug=slug,
        environment=environment,
        stack_name=deployment.stack_name,
        status=DeploymentStatus.DESTROYING,
        message="Destruction initiated",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
