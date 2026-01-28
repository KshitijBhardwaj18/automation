"""Customer configuration schema and loader."""

from dataclasses import dataclass

import pulumi


@dataclass
class CustomerConfig:
    """Configuration for a customer deployment."""

    # Customer identity
    customer_name: str
    environment: str

    # Cross-account access
    customer_role_arn: str
    external_id: pulumi.Output[str]
    aws_region: str

    # Networking
    vpc_cidr: str
    availability_zones: list[str]

    # EKS
    eks_version: str

    # Bootstrap component versions
    karpenter_version: str
    argocd_version: str
    cert_manager_version: str
    external_secrets_version: str
    ingress_nginx_version: str

    # ArgoCD GitOps configuration
    argocd_repo_url: str


def load_customer_config() -> CustomerConfig:
    """Load and validate customer configuration from Pulumi stack config."""
    config = pulumi.Config()

    # Parse availability zones from config (comma-separated string or list)
    az_config = config.get("availabilityZones")
    if az_config:
        availability_zones = [az.strip() for az in az_config.split(",")]
    else:
        # Default based on region
        region = config.get("awsRegion") or "us-east-1"
        availability_zones = [f"{region}a", f"{region}b", f"{region}c"]

    return CustomerConfig(
        # Customer identity
        customer_name=config.require("customerName"),
        environment=config.get("environment") or "prod",
        # Cross-account access
        customer_role_arn=config.require("customerRoleArn"),
        external_id=config.require_secret("externalId"),
        aws_region=config.get("awsRegion") or "us-east-1",
        # Networking
        vpc_cidr=config.get("vpcCidr") or "10.0.0.0/16",
        availability_zones=availability_zones,
        # EKS
        eks_version=config.get("eksVersion") or "1.31",
        # Bootstrap component versions
        karpenter_version=config.get("karpenterVersion") or "1.1.1",
        argocd_version=config.get("argocdVersion") or "7.7.16",
        cert_manager_version=config.get("certManagerVersion") or "v1.16.3",
        external_secrets_version=config.get("externalSecretsVersion") or "0.12.1",
        ingress_nginx_version=config.get("ingressNginxVersion") or "4.12.0",
        # ArgoCD GitOps configuration
        argocd_repo_url=config.get("argocdRepoUrl") or "",
    )
