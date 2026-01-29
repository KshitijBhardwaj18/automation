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
        customer_name=config.require("customerName"),
        environment=config.get("environment") or "prod",
        customer_role_arn=config.require("customerRoleArn"),
        external_id=config.require_secret("externalId"),
        aws_region=config.get("awsRegion") or "us-east-1",
        vpc_cidr=config.get("vpcCidr") or "10.0.0.0/16",
        availability_zones=availability_zones,
    )
