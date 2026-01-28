"""AWS and Kubernetes provider configuration with cross-account role assumption."""

import pulumi
import pulumi_aws as aws
import pulumi_kubernetes as k8s

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
                # 1 hour session duration (increase if deployments take longer)
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


def create_k8s_provider(
    name: str,
    kubeconfig: pulumi.Output[str],
    parent: pulumi.Resource,
) -> k8s.Provider:
    """Create Kubernetes provider from EKS kubeconfig.

    Args:
        name: Provider name prefix
        kubeconfig: EKS cluster kubeconfig (as JSON string)
        parent: Parent resource for dependency tracking
    """
    return k8s.Provider(
        f"{name}-k8s",
        kubeconfig=kubeconfig,
        opts=pulumi.ResourceOptions(parent=parent),
    )
