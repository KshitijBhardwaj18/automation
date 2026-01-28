"""Pulumi Deployments API client for triggering deployments."""

from typing import Any

import httpx

# Pulumi Cloud API base URL
PULUMI_API_BASE = "https://api.pulumi.com"


class PulumiDeploymentsClient:
    """Client for interacting with Pulumi Deployments API."""

    def __init__(
        self,
        organization: str,
        access_token: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
    ):
        """Initialize the Pulumi Deployments client.

        Args:
            organization: Pulumi organization name
            access_token: Pulumi access token
            aws_access_key_id: AWS access key ID for deployments
            aws_secret_access_key: AWS secret access key for deployments
        """
        self.organization = organization
        self.access_token = access_token
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

        self.headers = {
            "Authorization": f"token {self.access_token}",
            "Content-Type": "application/json",
        }

    async def create_stack(
        self,
        project_name: str,
        stack_name: str,
        esc_environment: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Pulumi stack.

        Args:
            project_name: Pulumi project name
            stack_name: Stack name to create
            esc_environment: Optional ESC environment path to link (e.g., "byoc-customers/test1-dev")

        Returns:
            API response
        """
        url = f"{PULUMI_API_BASE}/api/stacks/{self.organization}/{project_name}"

        payload: dict[str, Any] = {"stackName": stack_name}

        # Link ESC environment at stack creation time - no preRunCommand needed!
        if esc_environment:
            payload["config"] = {"environment": esc_environment}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def configure_deployment_settings(
        self,
        project_name: str,
        stack_name: str,
        repo_url: str,
        aws_region: str,
        repo_branch: str = "main",
        repo_dir: str = ".",
    ) -> dict[str, Any]:
        """Configure deployment settings for a stack.

        ESC environment is linked at stack creation time.
        Dependencies are auto-installed by Pulumi (skipInstallDependencies=False).
        No preRunCommands needed!

        Args:
            project_name: Pulumi project name
            stack_name: Stack name
            repo_url: Git repository URL containing Pulumi code
            aws_region: AWS region for deployment
            repo_branch: Git branch to deploy from
            repo_dir: Directory within repo containing Pulumi.yaml

        Returns:
            API response
        """
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments/settings"
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
                # No preRunCommands needed!
                # - ESC environment linked at stack creation
                # - Dependencies auto-installed by Pulumi
                "options": {
                    "skipInstallDependencies": False,
                },
                "environmentVariables": {
                    "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
                    "AWS_SECRET_ACCESS_KEY": {"secret": self.aws_secret_access_key},
                    "AWS_REGION": aws_region,
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
