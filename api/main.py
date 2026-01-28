"""FastAPI application for BYOC Platform."""

import json
import os
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException

from api.database import Database, db
from api.models import (
    CustomerDeployment,
    CustomerOffboardRequest,
    CustomerOnboardRequest,
    DeploymentResponse,
    DeploymentStatus,
)
from api.pulumi_deployments import PulumiDeploymentsClient

# Configuration
PULUMI_ORG = os.environ.get("PULUMI_ORG", "")
PULUMI_PROJECT = os.environ.get("PULUMI_PROJECT", "byoc-platform")
GIT_REPO_URL = os.environ.get("GIT_REPO_URL", "")
GIT_REPO_BRANCH = os.environ.get("GIT_REPO_BRANCH", "main")

app = FastAPI(
    title="BYOC Platform API",
    description="Multi-tenant BYOC (Bring Your Own Cloud) infrastructure deployment platform",
    version="1.0.0",
)


def get_pulumi_client() -> PulumiDeploymentsClient:
    """Get Pulumi Deployments client."""
    if not PULUMI_ORG:
        raise HTTPException(
            status_code=500,
            detail="PULUMI_ORG environment variable is required",
        )
    return PulumiDeploymentsClient(organization=PULUMI_ORG)


async def run_deployment(
    request: CustomerOnboardRequest,
    database: Database,
) -> None:
    """Background task to run customer deployment.

    Args:
        request: Customer onboarding request
        database: Database instance
    """
    stack_name = f"{request.customer_name}-{request.environment}"

    try:
        client = get_pulumi_client()

        # Update status to in progress
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.IN_PROGRESS,
        )

        # Create the stack if it doesn't exist
        try:
            await client.create_stack(
                project_name=PULUMI_PROJECT,
                stack_name=stack_name,
            )
        except Exception:
            # Stack might already exist, continue
            pass

        # Configure deployment settings
        await client.configure_deployment_settings(
            project_name=PULUMI_PROJECT,
            stack_name=stack_name,
            request=request,
            repo_url=GIT_REPO_URL,
            repo_branch=GIT_REPO_BRANCH,
        )

        # Trigger the deployment
        result = await client.trigger_deployment(
            project_name=PULUMI_PROJECT,
            stack_name=stack_name,
            operation="update",
        )

        deployment_id = result.get("id", "")

        # Update status with deployment ID
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.IN_PROGRESS,
            pulumi_deployment_id=deployment_id,
        )

        # Note: In production, you would poll for deployment completion
        # or use webhooks to get notified when the deployment finishes.
        # For now, we just mark it as in progress and let the user poll.

    except Exception as e:
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.FAILED,
            error_message=str(e),
        )


async def run_destroy(
    customer_name: str,
    environment: str,
    database: Database,
) -> None:
    """Background task to destroy customer infrastructure.

    Args:
        customer_name: Customer identifier
        environment: Environment name
        database: Database instance
    """
    stack_name = f"{customer_name}-{environment}"

    try:
        client = get_pulumi_client()

        # Update status to destroying
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.DESTROYING,
        )

        # Trigger destroy operation
        result = await client.trigger_deployment(
            project_name=PULUMI_PROJECT,
            stack_name=stack_name,
            operation="destroy",
        )

        deployment_id = result.get("id", "")

        # Update status with deployment ID
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.DESTROYING,
            pulumi_deployment_id=deployment_id,
        )

        # Note: In production, poll for completion then delete the stack

    except Exception as e:
        database.update_deployment_status(
            stack_name=stack_name,
            status=DeploymentStatus.FAILED,
            error_message=str(e),
        )


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/v1/customers/onboard", response_model=DeploymentResponse)
async def onboard_customer(
    request: CustomerOnboardRequest,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Onboard a new customer - provisions full infrastructure in their AWS account.

    This is an async operation. Use GET /api/v1/customers/{customer_name}/{environment}/status
    to check deployment progress.

    Args:
        request: Customer onboarding configuration
        background_tasks: FastAPI background tasks

    Returns:
        Deployment response with status
    """
    stack_name = f"{request.customer_name}-{request.environment}"

    # Check if deployment already exists
    existing = db.get_deployment(request.customer_name, request.environment)
    if existing:
        if existing.status == DeploymentStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=409,
                detail=f"Deployment {stack_name} is already in progress",
            )
        if existing.status == DeploymentStatus.SUCCEEDED:
            raise HTTPException(
                status_code=409,
                detail=f"Deployment {stack_name} already exists. Use update endpoint to modify.",
            )

    # Create deployment record
    try:
        db.create_deployment(
            customer_name=request.customer_name,
            environment=request.environment,
            aws_region=request.aws_region,
            role_arn=request.role_arn,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Run deployment in background
    background_tasks.add_task(run_deployment, request, db)

    return DeploymentResponse(
        customer_name=request.customer_name,
        environment=request.environment,
        stack_name=stack_name,
        status=DeploymentStatus.PENDING,
        message="Deployment initiated. Check status endpoint for progress.",
    )


@app.get(
    "/api/v1/customers/{customer_name}/{environment}/status",
    response_model=CustomerDeployment,
)
async def get_deployment_status(
    customer_name: str,
    environment: str = "prod",
) -> CustomerDeployment:
    """Get the current deployment status for a customer.

    Args:
        customer_name: Customer identifier
        environment: Environment name (default: prod)

    Returns:
        Customer deployment details
    """
    deployment = db.get_deployment(customer_name, environment)
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment for {customer_name}-{environment} not found",
        )

    # If deployment is in progress, check Pulumi for updates
    if deployment.status == DeploymentStatus.IN_PROGRESS and deployment.pulumi_deployment_id:
        try:
            client = get_pulumi_client()
            status = await client.get_deployment_status(
                project_name=PULUMI_PROJECT,
                stack_name=deployment.stack_name,
                deployment_id=deployment.pulumi_deployment_id,
            )

            pulumi_status = status.get("status", "")
            stack_name = deployment.stack_name
            if pulumi_status == "succeeded":
                # Get outputs
                outputs = await client.get_stack_outputs(
                    project_name=PULUMI_PROJECT,
                    stack_name=stack_name,
                )
                db.update_deployment_status(
                    stack_name=stack_name,
                    status=DeploymentStatus.SUCCEEDED,
                    outputs=json.dumps(outputs),
                )
                updated = db.get_deployment(customer_name, environment)
                if updated:
                    deployment = updated
            elif pulumi_status == "failed":
                db.update_deployment_status(
                    stack_name=stack_name,
                    status=DeploymentStatus.FAILED,
                    error_message=status.get("message", "Deployment failed"),
                )
                updated = db.get_deployment(customer_name, environment)
                if updated:
                    deployment = updated
        except Exception:
            # If we can't check status, just return current state
            pass

    # Convert to response model
    return CustomerDeployment(
        id=deployment.id,
        customer_name=deployment.customer_name,
        environment=deployment.environment,
        stack_name=deployment.stack_name,
        aws_region=deployment.aws_region,
        role_arn=deployment.role_arn,
        status=deployment.status,
        pulumi_deployment_id=deployment.pulumi_deployment_id,
        outputs=json.loads(deployment.outputs) if deployment.outputs else None,
        error_message=deployment.error_message,
        created_at=deployment.created_at,
        updated_at=deployment.updated_at,
    )


@app.get("/api/v1/customers/{customer_name}/{environment}/outputs")
async def get_customer_outputs(
    customer_name: str,
    environment: str = "prod",
) -> dict:
    """Get infrastructure outputs (VPC ID, EKS cluster name, etc.) for a customer.

    Args:
        customer_name: Customer identifier
        environment: Environment name (default: prod)

    Returns:
        Stack outputs
    """
    deployment = db.get_deployment(customer_name, environment)
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment for {customer_name}-{environment} not found",
        )

    if deployment.status != DeploymentStatus.SUCCEEDED:
        raise HTTPException(
            status_code=400,
            detail=f"Deployment is not complete. Current status: {deployment.status}",
        )

    if deployment.outputs:
        return json.loads(deployment.outputs)

    # Fetch from Pulumi if not cached
    try:
        client = get_pulumi_client()
        outputs = await client.get_stack_outputs(
            project_name=PULUMI_PROJECT,
            stack_name=deployment.stack_name,
        )

        # Cache outputs
        db.update_deployment_status(
            stack_name=deployment.stack_name,
            status=DeploymentStatus.SUCCEEDED,
            outputs=json.dumps(outputs),
        )

        return outputs
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch outputs: {str(e)}",
        )


@app.delete("/api/v1/customers/{customer_name}/{environment}")
async def offboard_customer(
    customer_name: str,
    environment: str,
    request: CustomerOffboardRequest,
    background_tasks: BackgroundTasks,
) -> DeploymentResponse:
    """Destroy all infrastructure for a customer (offboarding).

    Args:
        customer_name: Customer identifier
        environment: Environment name
        request: Offboard request with confirmation
        background_tasks: FastAPI background tasks

    Returns:
        Deployment response
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true to destroy infrastructure",
        )

    deployment = db.get_deployment(customer_name, environment)
    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment for {customer_name}-{environment} not found",
        )

    if deployment.status == DeploymentStatus.DESTROYING:
        raise HTTPException(
            status_code=409,
            detail="Destruction already in progress",
        )

    # Run destroy in background
    background_tasks.add_task(run_destroy, customer_name, environment, db)

    return DeploymentResponse(
        customer_name=customer_name,
        environment=environment,
        stack_name=deployment.stack_name,
        status=DeploymentStatus.DESTROYING,
        message="Destruction initiated. Check status endpoint for progress.",
    )


@app.get("/api/v1/customers", response_model=list[CustomerDeployment])
async def list_customers(
    customer_name: Optional[str] = None,
) -> list[CustomerDeployment]:
    """List all customer deployments.

    Args:
        customer_name: Optional filter by customer name

    Returns:
        List of customer deployments
    """
    deployments = db.list_deployments(customer_name=customer_name)

    return [
        CustomerDeployment(
            id=d.id,
            customer_name=d.customer_name,
            environment=d.environment,
            stack_name=d.stack_name,
            aws_region=d.aws_region,
            role_arn=d.role_arn,
            status=d.status,
            pulumi_deployment_id=d.pulumi_deployment_id,
            outputs=json.loads(d.outputs) if d.outputs else None,
            error_message=d.error_message,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in deployments
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
