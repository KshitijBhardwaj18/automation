"""AWS provider configuration with cross-account role assumption."""

import pulumi
import pulumi_aws as aws

from infra.config import CustomerConfig


def create_customer_aws_provider(config: CustomerConfig) -> aws.Provider:
    """Create AWS provider that assumes role in customer's AWS account.

    This enables cross-account deployments where your SaaS platform
    provisions infrastructure in customer AWS accounts.
    """
    return aws.Provider(
        "customer-aws",
        region=config.aws_region,
        assume_roles=[
            aws.ProviderAssumeRoleArgs(
                role_arn=config.customer_role_arn,
                external_id=config.external_id,
                session_name=f"pulumi-{pulumi.get_stack()}",
                duration="1h",
            )
        ],
        default_tags=aws.ProviderDefaultTagsArgs(
            tags={
                "ManagedBy": "Pulumi",
                "Environment": config.environment,
                "Customer": config.customer_name,
                "Stack": pulumi.get_stack(),
            },
        ),
    )
