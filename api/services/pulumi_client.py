"""Pulumi Deployments API client."""

from typing import Any

import httpx

from api.models import EnvironmentConfig, EksMode
from api.settings import settings

PULUMI_API_BASE = "https://api.pulumi.com"


class PulumiClient:
    """Client for Pulumi Deployments API."""

    def __init__(self):
        self.organization = settings.pulumi_org
        self.access_token = settings.pulumi_access_token
        self.aws_access_key_id = settings.aws_access_key_id
        self.aws_secret_access_key = settings.aws_secret_access_key
        self.github_token = settings.github_token or None

        self.headers = {
            "Authorization": f"token {self.access_token}",
            "Content-Type": "application/json",
        }

    async def create_stack(self, project_name: str, stack_name: str) -> dict[str, Any]:
        """Create a new Pulumi stack."""
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

    async def configure_deployment(
        self,
        project_name: str,
        stack_name: str,
        tenant_slug: str,
        environment: str,
        role_arn: str,
        external_id: str,
        aws_region: str,
        config: EnvironmentConfig,
    ) -> dict[str, Any]:
        """Configure deployment settings for a stack."""
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments/settings"
        )

        stack_id = f"{self.organization}/{project_name}/{stack_name}"

        pre_run_commands = [
            f"pulumi config set --stack {stack_id} customerName {tenant_slug}",
            f"pulumi config set --stack {stack_id} environment {environment}",
            f"pulumi config set --stack {stack_id} customerRoleArn {role_arn}",
            f"pulumi config set --stack {stack_id} --secret externalId {external_id}",
            f"pulumi config set --stack {stack_id} awsRegion {aws_region}",
            f"pulumi config set --stack {stack_id} vpcCidr {config.vpc_cidr}",
            f"pulumi config set --stack {stack_id} eksVersion {config.eks_version}",
            f"pulumi config set --stack {stack_id} eksMode {config.eks_mode.value}",
        ]

        if config.availability_zones:
            az_str = ",".join(config.availability_zones)
            pre_run_commands.append(
                f"pulumi config set --stack {stack_id} availabilityZones {az_str}"
            )

        if config.eks_mode == EksMode.MANAGED:
            ng = config.node_group_config
            if ng:
                pre_run_commands.extend([
                    f"pulumi config set --stack {stack_id} nodeInstanceTypes {','.join(ng.instance_types)}",
                    f"pulumi config set --stack {stack_id} nodeDesiredSize {ng.desired_size}",
                    f"pulumi config set --stack {stack_id} nodeMinSize {ng.min_size}",
                    f"pulumi config set --stack {stack_id} nodeMaxSize {ng.max_size}",
                    f"pulumi config set --stack {stack_id} nodeDiskSize {ng.disk_size}",
                    f"pulumi config set --stack {stack_id} nodeCapacityType {ng.capacity_type}",
                ])
            else:
                pre_run_commands.extend([
                    f"pulumi config set --stack {stack_id} nodeInstanceTypes t3.medium",
                    f"pulumi config set --stack {stack_id} nodeDesiredSize 2",
                    f"pulumi config set --stack {stack_id} nodeMinSize 1",
                    f"pulumi config set --stack {stack_id} nodeMaxSize 5",
                    f"pulumi config set --stack {stack_id} nodeDiskSize 50",
                    f"pulumi config set --stack {stack_id} nodeCapacityType ON_DEMAND",
                ])

        source_context: dict[str, Any] = {
            "git": {
                "repoUrl": settings.git_repo_url,
                "branch": f"refs/heads/{settings.git_repo_branch}",
                "repoDir": settings.git_repo_dir,
            }
        }

        if self.github_token:
            source_context["git"]["gitAuth"] = {
                "accessToken": {"secret": self.github_token}
            }

        payload = {
            "sourceContext": source_context,
            "operationContext": {
                "preRunCommands": pre_run_commands,
                "environmentVariables": {
                    "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
                    "AWS_SECRET_ACCESS_KEY": {"secret": self.aws_secret_access_key},
                    "AWS_REGION": aws_region,
                },
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=self.headers, json=payload, timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def trigger_deployment(
        self,
        project_name: str,
        stack_name: str,
        operation: str = "update",
    ) -> dict[str, Any]:
        """Trigger a Pulumi deployment."""
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={"operation": operation, "inheritSettings": True},
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
        """Get deployment status."""
        url = (
            f"{PULUMI_API_BASE}/api/stacks/{self.organization}/"
            f"{project_name}/{stack_name}/deployments/{deployment_id}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            response.raise_for_status()
            return response.json()

    async def get_stack_outputs(
        self, project_name: str, stack_name: str
    ) -> dict[str, Any]:
        """Get stack outputs."""
        url = f"{PULUMI_API_BASE}/api/stacks/{self.organization}/{project_name}/{stack_name}/export"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            resources = data.get("deployment", {}).get("resources", [])
            for resource in resources:
                if resource.get("type") == "pulumi:pulumi:Stack":
                    return resource.get("outputs", {})
            return {}


def get_pulumi_client() -> PulumiClient:
    """Get Pulumi client instance."""
    return PulumiClient()
