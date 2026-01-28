"""Pulumi ESC (Environments, Secrets, Configuration) client for managing customer environments."""

from typing import Any

import httpx
import yaml

# Pulumi Cloud API base URL
PULUMI_API_BASE = "https://api.pulumi.com"


class PulumiESCClient:
    """Client for managing Pulumi ESC environments."""

    def __init__(
        self,
        organization: str,
        access_token: str,
    ):
        """Initialize the ESC client.

        Args:
            organization: Pulumi organization name
            access_token: Pulumi access token
        """
        self.organization = organization
        self.access_token = access_token
        self.headers = {
            "Authorization": f"token {self.access_token}",
            "Content-Type": "application/json",
        }

    async def create_environment(
        self,
        project_name: str,
        env_name: str,
    ) -> dict[str, Any]:
        """Create a new ESC environment.

        Args:
            project_name: ESC project name (e.g., "byoc-customers")
            env_name: Environment name (e.g., "customer1-dev")

        Returns:
            API response
        """
        url = f"{PULUMI_API_BASE}/api/esc/environments/{self.organization}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={
                    "project": project_name,
                    "name": env_name,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            # POST returns empty on success, return useful info
            return {"project": project_name, "name": env_name, "status": "created"}

    async def update_environment(
        self,
        project_name: str,
        env_name: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an ESC environment definition.

        Args:
            project_name: ESC project name
            env_name: Environment name
            definition: Environment definition (YAML structure as dict)

        Returns:
            API response
        """
        url = (
            f"{PULUMI_API_BASE}/api/esc/environments/{self.organization}/{project_name}/{env_name}"
        )

        # Convert definition to YAML string
        yaml_content = yaml.dump(definition, default_flow_style=False)

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                url,
                headers={
                    **self.headers,
                    "Content-Type": "application/x-yaml",
                },
                content=yaml_content,
                timeout=30.0,
            )
            response.raise_for_status()
            # PATCH returns empty {} on success
            return {"status": "updated"}

    async def get_environment(
        self,
        project_name: str,
        env_name: str,
    ) -> dict[str, Any]:
        """Get an ESC environment definition.

        Args:
            project_name: ESC project name
            env_name: Environment name

        Returns:
            Environment definition
        """
        url = (
            f"{PULUMI_API_BASE}/api/esc/environments/{self.organization}/{project_name}/{env_name}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def delete_environment(
        self,
        project_name: str,
        env_name: str,
    ) -> None:
        """Delete an ESC environment.

        Args:
            project_name: ESC project name
            env_name: Environment name
        """
        url = (
            f"{PULUMI_API_BASE}/api/esc/environments/{self.organization}/{project_name}/{env_name}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                url,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()

    async def list_environments(
        self,
        project_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List ESC environments.

        Args:
            project_name: Optional project name to filter by

        Returns:
            List of environments
        """
        url = f"{PULUMI_API_BASE}/api/esc/environments/{self.organization}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            environments = data.get("environments", [])
            if project_name:
                environments = [e for e in environments if e.get("project") == project_name]
            return environments

    def build_customer_environment_definition(
        self,
        customer_name: str,
        environment: str,
        role_arn: str,
        external_id: str,
        aws_region: str,
        vpc_cidr: str = "10.0.0.0/16",
        availability_zones: list[str] | None = None,
        eks_version: str = "1.31",
        karpenter_version: str = "1.1.1",
        argocd_version: str = "7.7.16",
        cert_manager_version: str = "v1.16.3",
        external_secrets_version: str = "0.12.1",
        ingress_nginx_version: str = "4.12.0",
        argocd_repo_url: str = "",
    ) -> dict[str, Any]:
        """Build ESC environment definition for a customer.

        This creates a YAML structure that will be used as the environment definition.
        The pulumiConfig section maps values to Pulumi stack configuration.

        Args:
            customer_name: Customer identifier
            environment: Environment name (dev, staging, prod)
            role_arn: AWS IAM role ARN for cross-account access
            external_id: External ID for role assumption (secret)
            aws_region: AWS region
            vpc_cidr: VPC CIDR block
            availability_zones: List of availability zones
            eks_version: EKS Kubernetes version
            karpenter_version: Karpenter Helm chart version
            argocd_version: ArgoCD Helm chart version
            cert_manager_version: Cert-manager version
            external_secrets_version: External Secrets Operator version
            ingress_nginx_version: Ingress NGINX version
            argocd_repo_url: ArgoCD GitOps repository URL

        Returns:
            Environment definition as dict (to be converted to YAML)
        """
        # Default availability zones based on region
        if not availability_zones:
            availability_zones = [
                f"{aws_region}a",
                f"{aws_region}b",
                f"{aws_region}c",
            ]

        return {
            "values": {
                # Customer configuration
                "customer": {
                    "name": customer_name,
                    "environment": environment,
                },
                # AWS configuration
                "aws": {
                    "region": aws_region,
                    "roleArn": role_arn,
                    "externalId": {"fn::secret": external_id},
                },
                # Networking configuration
                "networking": {
                    "vpcCidr": vpc_cidr,
                    "availabilityZones": ",".join(availability_zones),
                },
                # EKS configuration
                "eks": {
                    "version": eks_version,
                },
                # Bootstrap component versions
                "bootstrap": {
                    "karpenterVersion": karpenter_version,
                    "argocdVersion": argocd_version,
                    "certManagerVersion": cert_manager_version,
                    "externalSecretsVersion": external_secrets_version,
                    "ingressNginxVersion": ingress_nginx_version,
                    "argocdRepoUrl": argocd_repo_url,
                },
                # Pulumi stack configuration - maps to config keys
                "pulumiConfig": {
                    "byoc-platform:customerName": "${customer.name}",
                    "byoc-platform:environment": "${customer.environment}",
                    "byoc-platform:customerRoleArn": "${aws.roleArn}",
                    "byoc-platform:externalId": "${aws.externalId}",
                    "byoc-platform:awsRegion": "${aws.region}",
                    "byoc-platform:vpcCidr": "${networking.vpcCidr}",
                    "byoc-platform:availabilityZones": "${networking.availabilityZones}",
                    "byoc-platform:eksVersion": "${eks.version}",
                    "byoc-platform:karpenterVersion": "${bootstrap.karpenterVersion}",
                    "byoc-platform:argocdVersion": "${bootstrap.argocdVersion}",
                    "byoc-platform:certManagerVersion": "${bootstrap.certManagerVersion}",
                    "byoc-platform:externalSecretsVersion": "${bootstrap.externalSecretsVersion}",
                    "byoc-platform:ingressNginxVersion": "${bootstrap.ingressNginxVersion}",
                    "byoc-platform:argocdRepoUrl": "${bootstrap.argocdRepoUrl}",
                },
            },
        }
