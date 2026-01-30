"""Tenant service."""

import secrets
import uuid

from api.database import db, TenantRecord
from api.models import Tenant, TenantCreate, TenantResponse


class TenantService:
    """Service for tenant operations."""

    def create(self, request: TenantCreate) -> TenantResponse:
        """Create a new tenant."""
        tenant_id = str(uuid.uuid4())
        external_id = secrets.token_urlsafe(32)
        role_arn = f"arn:aws:iam::{request.aws_account_id}:role/BYOCPlatformRole"

        record = db.create_tenant(
            id=tenant_id,
            slug=request.slug,
            name=request.name,
            aws_account_id=request.aws_account_id,
            aws_region=request.aws_region,
            role_arn=role_arn,
            external_id=external_id,
        )

        return TenantResponse(
            tenant=self._to_model(record),
            message="Tenant created. Save the external_id - it won't be shown again.",
        )

    def get_by_slug(self, slug: str) -> Tenant | None:
        """Get tenant by slug."""
        record = db.get_tenant_by_slug(slug)
        return self._to_model(record) if record else None

    def list_all(self) -> list[Tenant]:
        """List all tenants."""
        return [self._to_model(r) for r in db.list_tenants()]

    def delete(self, slug: str) -> bool:
        """Delete tenant."""
        return db.delete_tenant(slug)

    def _to_model(self, record: TenantRecord) -> Tenant:
        """Convert record to model."""
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


tenant_service = TenantService()
