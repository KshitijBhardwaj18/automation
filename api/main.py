"""FastAPI application for BYOC Platform."""

from fastapi import FastAPI

from api.routers import config, deployments, tenants

app = FastAPI(
    title="BYOC Platform API",
    description="Multi-tenant BYOC infrastructure deployment platform",
    version="2.0.0",
)

# Routers
app.include_router(tenants.router)
app.include_router(config.router)
app.include_router(deployments.router)


@app.get("/health")
async def health_check() -> dict:
    """Health check."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
