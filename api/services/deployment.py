"""Deployment service."""

import json

from api.database import db, TenantRecord, DeploymentRecord
from api.models import Deployment, DeploymentStatus, EnvironmentConfig
from api.services.pulumi_client import get_pulumi_client
from api.settings import settings


class DeploymentService:
    """Service for deployment operations."""

    async def deploy(
        self,
        tenant: TenantRecord,
        environment: str,
        config: EnvironmentConfig,
    ) -> None:
        """Run deployment."""
        stack_name = f"{tenant.slug}-{environment}"

        try:
            client = get_pulumi_client()

            db.update_deployment_status(
                stack_name=stack_name,
                status=DeploymentStatus.IN_PROGRESS,
            )

            # Create stack if needed
            try:
                await client.create_stack(settings.pulumi_project, stack_name)
            except Exception:
                pass

            # Configure and trigger
            await client.configure_deployment(
                project_name=settings.pulumi_project,
                stack_name=stack_name,
                tenant_slug=tenant.slug,
                environment=environment,
                role_arn=tenant.role_arn,
                external_id=tenant.external_id,
                aws_region=tenant.aws_region,
                config=config,
            )

            result = await client.trigger_deployment(
                settings.pulumi_project, stack_name, "update"
            )

            db.update_deployment_status(
                stack_name=stack_name,
                status=DeploymentStatus.IN_PROGRESS,
                pulumi_deployment_id=result.get("id", ""),
            )

        except Exception as e:
            db.update_deployment_status(
                stack_name=stack_name,
                status=DeploymentStatus.FAILED,
                error_message=str(e),
            )

    async def destroy(self, tenant_slug: str, environment: str) -> None:
        """Destroy infrastructure."""
        stack_name = f"{tenant_slug}-{environment}"

        try:
            client = get_pulumi_client()

            db.update_deployment_status(
                stack_name=stack_name,
                status=DeploymentStatus.DESTROYING,
            )

            result = await client.trigger_deployment(
                settings.pulumi_project, stack_name, "destroy"
            )

            db.update_deployment_status(
                stack_name=stack_name,
                status=DeploymentStatus.DESTROYING,
                pulumi_deployment_id=result.get("id", ""),
            )

        except Exception as e:
            db.update_deployment_status(
                stack_name=stack_name,
                status=DeploymentStatus.FAILED,
                error_message=str(e),
            )

    async def sync_status(self, tenant_slug: str, environment: str) -> Deployment | None:
        """Sync and return deployment status."""
        record = db.get_deployment(tenant_slug, environment)
        if not record:
            return None

        # Check Pulumi for updates if in progress
        if record.status == DeploymentStatus.IN_PROGRESS and record.pulumi_deployment_id:
            try:
                client = get_pulumi_client()
                status = await client.get_deployment_status(
                    settings.pulumi_project,
                    record.stack_name,
                    record.pulumi_deployment_id,
                )

                pulumi_status = status.get("status", "")
                if pulumi_status == "succeeded":
                    outputs = await client.get_stack_outputs(
                        settings.pulumi_project, record.stack_name
                    )
                    db.update_deployment_status(
                        stack_name=record.stack_name,
                        status=DeploymentStatus.SUCCEEDED,
                        outputs=json.dumps(outputs),
                    )
                    record = db.get_deployment(tenant_slug, environment)
                elif pulumi_status == "failed":
                    db.update_deployment_status(
                        stack_name=record.stack_name,
                        status=DeploymentStatus.FAILED,
                        error_message=status.get("message", "Deployment failed"),
                    )
                    record = db.get_deployment(tenant_slug, environment)
            except Exception:
                pass

        return self._to_model(record) if record else None

    def _to_model(self, record: DeploymentRecord) -> Deployment:
        """Convert record to model."""
        return Deployment(
            id=record.id,
            tenant_id=record.tenant_id,
            tenant_slug=record.tenant_slug,
            environment=record.environment,
            stack_name=record.stack_name,
            aws_region=record.aws_region,
            status=record.status,
            pulumi_deployment_id=record.pulumi_deployment_id,
            outputs=json.loads(record.outputs) if record.outputs else None,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


deployment_service = DeploymentService()
