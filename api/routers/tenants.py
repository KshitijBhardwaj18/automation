"""Tenant endpoints."""

from fastapi import APIRouter, HTTPException

from api.database import db
from api.models import DeploymentStatus, Tenant, TenantCreate, TenantResponse
from api.services.tenant import tenant_service

router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants"])


@router.post("", response_model=TenantResponse)
async def create_tenant(request: TenantCreate) -> TenantResponse:
    """Create a new tenant."""
    try:
        return tenant_service.create(request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[Tenant])
async def list_tenants() -> list[Tenant]:
    """List all tenants."""
    return tenant_service.list_all()


@router.get("/{slug}", response_model=Tenant)
async def get_tenant(slug: str) -> Tenant:
    """Get tenant by slug."""
    tenant = tenant_service.get_by_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")
    return tenant


@router.delete("/{slug}")
async def delete_tenant(slug: str) -> dict:
    """Delete tenant."""
    # Check for active deployments
    deployments = db.list_deployments(tenant_slug=slug)
    active = [
        d for d in deployments
        if d.status not in [DeploymentStatus.DESTROYED, DeploymentStatus.FAILED]
    ]
    if active:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete tenant with active deployments",
        )

    if not tenant_service.delete(slug):
        raise HTTPException(status_code=404, detail=f"Tenant '{slug}' not found")

    return {"message": f"Tenant '{slug}' deleted"}
