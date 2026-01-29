"""BYOC Platform - Main entry point for Pulumi infrastructure deployment."""

import pulumi

from infra.components.networking import Networking
from infra.config import load_customer_config
from infra.providers import create_customer_aws_provider

# Load customer configuration from stack config
config = load_customer_config()

# Create AWS provider that assumes role in customer's account
aws_provider = create_customer_aws_provider(config)

# Networking (VPC, subnets, NAT gateways)
networking = Networking(
    name=config.customer_name,
    vpc_cidr=config.vpc_cidr,
    availability_zones=config.availability_zones,
    provider=aws_provider,
)

# Exports
pulumi.export("vpc_id", networking.vpc_id)
pulumi.export("private_subnet_ids", networking.private_subnet_ids)
pulumi.export("public_subnet_ids", networking.public_subnet_ids)
