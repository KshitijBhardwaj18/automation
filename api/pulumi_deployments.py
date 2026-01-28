"""Pulumi Deployments API client for triggering deployments."""

import os
from typing import Any, Optional

import httpx

from api.models import CustomerOnboardRequest

# Pulumi Cloud API base URL
PULUMI_API_BASE = "https://api.pulumi.com"


class PulumiDeploymentsClient:
    """Client for interacting with Pulumi Deployments API."""

    def __init__(
        self,
        organization: str,
        access_token: Optional[str] = None,
    ):
        """Initialize the Pulumi Deployments client.

        Args:
            organization: Pulumi organization name
            access_token: Pulumi access token (defaults to PULUMI_ACCESS_TOKEN env var)
        """
        self.organization = organization
        self.access_token = access_token or os.environ.get("PULUMI_ACCESS_TOKEN", "")
        if not self.access_token:
            raise ValueError(
                "PULUMI_ACCESS_TOKEN environment variable is required "
                "or pass access_token parameter"
            )

        self.headers = {
            "Authorization": f"token {self.access_token}",
            "Content-Type": "application/json",
        }

    async def create_stack(
        self,
        project_name: str,
        stack_name: str,
    ) -> dict[str, Any]:
        """Create a new Pulumi stack.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name to create

        Returns:
            API response
        """
        url = f"{PULUMI_API_BASE}/api/stacks/{self.organization}/{project_name}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={"stackName": stack_name},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def configure_deployment_settings(
        self,
        project_name: str,
        stack_name: str,
        request: CustomerOnboardRequest,
        repo_url: str,
        repo_branch: str = "main",
        repo_dir: str = ".",
    ) -> dict[str, Any]:
        """Configure deployment settings for a stack.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name
            request: Customer onboarding request with configuration
            repo_url: Git repository URL containing Pulumi code
            repo_branch: Git branch to deploy from
            repo_dir: Directory within repo containing Pulumi.yaml

        Returns:
            API response
        """
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments/settings"
        )

        # Build stack configuration from customer request
        stack_config = {
            f"{project_name}:customerName": request.customer_name,
            f"{project_name}:environment": request.environment,
            f"{project_name}:customerRoleArn": request.role_arn,
            f"{project_name}:awsRegion": request.aws_region,
            f"{project_name}:vpcCidr": request.vpc_cidr,
            f"{project_name}:eksVersion": request.eks_version,
            f"{project_name}:karpenterVersion": request.karpenter_version,
            f"{project_name}:argocdVersion": request.argocd_version,
            f"{project_name}:certManagerVersion": request.cert_manager_version,
            f"{project_name}:externalSecretsVersion": request.external_secrets_version,
            f"{project_name}:ingressNginxVersion": request.ingress_nginx_version,
        }

        if request.availability_zones:
            stack_config[f"{project_name}:availabilityZones"] = ",".join(request.availability_zones)

        if request.argocd_repo_url:
            stack_config[f"{project_name}:argocdRepoUrl"] = request.argocd_repo_url

        settings = {
            "sourceContext": {
                "git": {
                    "repoUrl": repo_url,
                    "branch": f"refs/heads/{repo_branch}",
                    "repoDir": repo_dir,
                }
            },
            "operationContext": {
                "preRunCommands": [
                    "pip install -r requirements.txt",
                ],
                "environmentVariables": {
                    # Stack config values are set via pulumi config
                    "PULUMI_CONFIG": self._encode_config(stack_config),
                },
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json=settings,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def set_stack_config(
        self,
        project_name: str,
        stack_name: str,
        request: CustomerOnboardRequest,
    ) -> None:
        """Set stack configuration values including secrets.

        This uses the Pulumi CLI via the API to set config values,
        including the external_id as a secret.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name
            request: Customer onboarding request
        """
        # Note: In production, you would use the Pulumi Automation API
        # or CLI to set these config values, especially secrets.
        # The Deployments API doesn't directly support setting secrets.
        # This is a placeholder for the config that needs to be set.
        pass

    def _encode_config(self, config: dict[str, str]) -> str:
        """Encode config dict as environment variable format.

        Args:
            config: Configuration key-value pairs

        Returns:
            Encoded config string
        """
        # Pulumi can read config from environment variables
        # Format: key=value pairs
        return ";".join(f"{k}={v}" for k, v in config.items())

    async def trigger_deployment(
        self,
        project_name: str,
        stack_name: str,
        operation: str = "update",
        inherit_settings: bool = True,
    ) -> dict[str, Any]:
        """Trigger a Pulumi deployment.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name to deploy
            operation: Pulumi operation (update, preview, refresh, destroy)
            inherit_settings: Whether to use stack deployment settings

        Returns:
            API response with deployment ID
        """
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments"
        )

        payload = {
            "operation": operation,
            "inheritSettings": inherit_settings,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_deployment_status(
        self,
        project_name: str,
        stack_name: str,
        deployment_id: str,
    ) -> dict[str, Any]:
        """Get the status of a deployment.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name
            deployment_id: Deployment ID to check

        Returns:
            Deployment status
        """
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments/{deployment_id}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_stack_outputs(
        self,
        project_name: str,
        stack_name: str,
    ) -> dict[str, Any]:
        """Get stack outputs.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name

        Returns:
            Stack outputs
        """
        url = f"{PULUMI_API_BASE}/api/stacks/{self.organization}/{project_name}/{stack_name}/export"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            # Extract outputs from stack state
            deployment = data.get("deployment", {})
            resources = deployment.get("resources", [])

            # Find the stack resource which contains outputs
            for resource in resources:
                if resource.get("type") == "pulumi:pulumi:Stack":
                    return resource.get("outputs", {})

            return {}

    async def delete_stack(
        self,
        project_name: str,
        stack_name: str,
        force: bool = False,
    ) -> None:
        """Delete a Pulumi stack.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name to delete
            force: Force delete even if resources exist
        """
        url = f"{PULUMI_API_BASE}/api/stacks/{self.organization}/{project_name}/{stack_name}"
        if force:
            url += "?force=true"

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                url,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()
