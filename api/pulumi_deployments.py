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
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        """Initialize the Pulumi Deployments client.

        Args:
            organization: Pulumi organization name
            access_token: Pulumi access token (defaults to PULUMI_ACCESS_TOKEN env var)
            aws_access_key_id: AWS access key ID (defaults to AWS_ACCESS_KEY_ID env var)
            aws_secret_access_key: AWS secret access key (defaults to AWS_SECRET_ACCESS_KEY env var)
        """
        self.organization = organization
        self.access_token = access_token or os.environ.get("PULUMI_ACCESS_TOKEN", "")
        if not self.access_token:
            raise ValueError(
                "PULUMI_ACCESS_TOKEN environment variable is required "
                "or pass access_token parameter"
            )

        # AWS credentials for deployments
        self.aws_access_key_id = aws_access_key_id or os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_access_key = aws_secret_access_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        if not self.aws_access_key_id or not self.aws_secret_access_key:
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables are required "
                "or pass aws_access_key_id and aws_secret_access_key parameters"
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

        # Full stack identifier for pulumi config commands
        stack_id = f"{self.organization}/{project_name}/{stack_name}"

        # Build pre-run commands to set stack configuration
        # Use --stack flag to ensure correct stack is targeted
        pre_run_commands = [
            "pip install -r requirements.txt",
            f"pulumi config set --stack {stack_id} customerName {request.customer_name}",
            f"pulumi config set --stack {stack_id} environment {request.environment}",
            f"pulumi config set --stack {stack_id} customerRoleArn {request.role_arn}",
            f"pulumi config set --stack {stack_id} --secret externalId {request.external_id}",
            f"pulumi config set --stack {stack_id} awsRegion {request.aws_region}",
            f"pulumi config set --stack {stack_id} vpcCidr {request.vpc_cidr}",
            f"pulumi config set --stack {stack_id} eksVersion {request.eks_version}",
            f"pulumi config set --stack {stack_id} karpenterVersion {request.karpenter_version}",
            f"pulumi config set --stack {stack_id} argocdVersion {request.argocd_version}",
            f"pulumi config set --stack {stack_id} certManagerVersion {request.cert_manager_version}",
            f"pulumi config set --stack {stack_id} externalSecretsVersion {request.external_secrets_version}",
            f"pulumi config set --stack {stack_id} ingressNginxVersion {request.ingress_nginx_version}",
        ]

        # Add availability zones if provided
        if request.availability_zones:
            az_str = ",".join(request.availability_zones)
            pre_run_commands.append(
                f"pulumi config set --stack {stack_id} availabilityZones {az_str}"
            )

        # Add ArgoCD repo URL if provided
        if request.argocd_repo_url:
            pre_run_commands.append(
                f"pulumi config set --stack {stack_id} argocdRepoUrl {request.argocd_repo_url}"
            )

        settings = {
            "sourceContext": {
                "git": {
                    "repoUrl": repo_url,
                    "branch": f"refs/heads/{repo_branch}",
                    "repoDir": repo_dir,
                }
            },
            "operationContext": {
                "preRunCommands": pre_run_commands,
                "environmentVariables": {
                    "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
                    "AWS_SECRET_ACCESS_KEY": {"secret": self.aws_secret_access_key},
                    "AWS_REGION": request.aws_region,
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
