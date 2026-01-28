"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeploymentStatus(str, Enum):
    """Status of a customer deployment."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


class CustomerOnboardRequest(BaseModel):
    """Request to onboard a new customer."""

    # Customer identity
    customer_name: str = Field(
        ...,
        description="Unique customer identifier (used in stack name)",
        pattern=r"^[a-z0-9-]+$",
        min_length=3,
        max_length=50,
    )
    environment: str = Field(
        default="prod",
        description="Environment name (dev/staging/prod)",
        pattern=r"^[a-z0-9-]+$",
    )

    # Cross-account access
    role_arn: str = Field(
        ...,
        description="Customer's IAM role ARN for cross-account access",
        pattern=r"^arn:aws:iam::\d{12}:role/.+$",
    )
    external_id: str = Field(
        ...,
        description="External ID for secure role assumption",
        min_length=10,
    )

    # AWS configuration
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for deployment",
    )

    # Networking
    vpc_cidr: str = Field(
        default="10.0.0.0/16",
        description="VPC CIDR block",
    )
    availability_zones: Optional[list[str]] = Field(
        default=None,
        description="Availability zones (defaults to 3 AZs in the region)",
    )

    # EKS configuration
    eks_version: str = Field(
        default="1.31",
        description="EKS Kubernetes version",
    )

    # Bootstrap component versions
    karpenter_version: str = Field(default="1.1.1")
    argocd_version: str = Field(default="7.7.16")
    cert_manager_version: str = Field(default="v1.16.3")
    external_secrets_version: str = Field(default="0.12.1")
    ingress_nginx_version: str = Field(default="4.12.0")

    # ArgoCD GitOps configuration
    argocd_repo_url: Optional[str] = Field(
        default=None,
        description="GitOps repository URL for ArgoCD",
    )


class CustomerDeployment(BaseModel):
    """Customer deployment record."""

    id: int
    customer_name: str
    environment: str
    stack_name: str
    aws_region: str
    role_arn: str
    status: DeploymentStatus
    pulumi_deployment_id: Optional[str] = None
    outputs: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeploymentResponse(BaseModel):
    """Response for deployment operations."""

    customer_name: str
    environment: str
    stack_name: str
    status: DeploymentStatus
    message: str
    deployment_id: Optional[str] = None


class CustomerOffboardRequest(BaseModel):
    """Request to offboard (destroy) a customer's infrastructure."""

    customer_name: str = Field(..., description="Customer identifier")
    environment: str = Field(default="prod", description="Environment name")
    confirm: bool = Field(
        default=False,
        description="Must be true to confirm destruction",
    )
