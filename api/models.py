"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class DeploymentStatus(str, Enum):
    """Status of a deployment."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


class EksMode(str, Enum):
    """EKS compute mode."""

    AUTO = "auto"
    MANAGED = "managed"


# =============================================================================
# TENANT MODELS
# =============================================================================


class TenantCreate(BaseModel):
    """Request to create a new tenant."""

    name: str = Field(
        ...,
        description="Display name for the tenant",
        min_length=2,
        max_length=100,
    )
    slug: str = Field(
        ...,
        description="Unique URL-friendly identifier (used in stack names)",
        pattern=r"^[a-z0-9-]+$",
        min_length=3,
        max_length=50,
    )
    aws_account_id: str = Field(
        ...,
        description="AWS Account ID (12 digits)",
        pattern=r"^\d{12}$",
    )
    aws_region: str = Field(
        default="us-east-1",
        description="Default AWS region for deployments",
    )


class Tenant(BaseModel):
    """Tenant record."""

    id: str
    slug: str
    name: str
    aws_account_id: str
    aws_region: str
    role_arn: str
    external_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantResponse(BaseModel):
    """Response after creating a tenant."""

    tenant: Tenant
    message: str


# =============================================================================
# ENVIRONMENT CONFIG MODELS
# =============================================================================


class NodeGroupConfig(BaseModel):
    """Configuration for managed node group."""

    instance_types: list[str] = Field(default=["t3.medium"])
    desired_size: int = Field(default=2, ge=1, le=100)
    min_size: int = Field(default=1, ge=1, le=100)
    max_size: int = Field(default=5, ge=1, le=100)
    disk_size: int = Field(default=50, ge=20, le=1000)
    capacity_type: str = Field(default="ON_DEMAND", pattern=r"^(ON_DEMAND|SPOT)$")


class EnvironmentConfig(BaseModel):
    """Configuration for a tenant's environment."""

    vpc_cidr: str = Field(default="10.0.0.0/16")
    availability_zones: Optional[list[str]] = Field(default=None)
    eks_version: str = Field(default="1.31")
    eks_mode: EksMode = Field(default=EksMode.MANAGED)
    node_group_config: Optional[NodeGroupConfig] = Field(default=None)


class ConfigResponse(BaseModel):
    """Response for config operations."""

    tenant_slug: str
    environment: str
    message: str
    config: Optional[EnvironmentConfig] = None


# =============================================================================
# DEPLOYMENT MODELS
# =============================================================================


class DeployRequest(BaseModel):
    """Request to deploy (empty body - config already saved)."""

    pass


class DestroyRequest(BaseModel):
    """Request to destroy infrastructure."""

    confirm: bool = Field(default=False)


class DeploymentResponse(BaseModel):
    """Response for deployment operations."""

    tenant_slug: str
    environment: str
    stack_name: str
    status: DeploymentStatus
    message: str
    deployment_id: Optional[str] = None


class Deployment(BaseModel):
    """Deployment record."""

    id: int
    tenant_id: str
    tenant_slug: str
    environment: str
    stack_name: str
    aws_region: str
    status: DeploymentStatus
    pulumi_deployment_id: Optional[str] = None
    outputs: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
