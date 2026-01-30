"""SQLite database for tenants and deployments."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from api.models import DeploymentStatus


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class TenantRecord(Base):
    """Database model for tenants."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    aws_account_id: Mapped[str] = mapped_column(String(12), nullable=False)
    aws_region: Mapped[str] = mapped_column(String(20), nullable=False)
    role_arn: Mapped[str] = mapped_column(String(200), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DeploymentRecord(Base):
    """Database model for deployments."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    stack_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    aws_region: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus), nullable=False, default=DeploymentStatus.PENDING
    )
    pulumi_deployment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    outputs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Database:
    """Database operations."""

    def __init__(self, database_url: str = "sqlite:///./byoc_platform.db"):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    # =========================================================================
    # TENANT OPERATIONS
    # =========================================================================

    def create_tenant(
        self,
        id: str,
        slug: str,
        name: str,
        aws_account_id: str,
        aws_region: str,
        role_arn: str,
        external_id: str,
    ) -> TenantRecord:
        """Create a new tenant."""
        with self.get_session() as session:
            # Check if slug already exists
            existing = session.query(TenantRecord).filter_by(slug=slug).first()
            if existing:
                raise ValueError(f"Tenant with slug '{slug}' already exists")

            record = TenantRecord(
                id=id,
                slug=slug,
                name=name,
                aws_account_id=aws_account_id,
                aws_region=aws_region,
                role_arn=role_arn,
                external_id=external_id,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_tenant_by_slug(self, slug: str) -> Optional[TenantRecord]:
        """Get tenant by slug."""
        with self.get_session() as session:
            return session.query(TenantRecord).filter_by(slug=slug).first()

    def list_tenants(self) -> list[TenantRecord]:
        """List all tenants."""
        with self.get_session() as session:
            return session.query(TenantRecord).all()

    def delete_tenant(self, slug: str) -> bool:
        """Delete tenant."""
        with self.get_session() as session:
            record = session.query(TenantRecord).filter_by(slug=slug).first()
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    # =========================================================================
    # DEPLOYMENT OPERATIONS
    # =========================================================================

    def create_deployment(
        self,
        tenant_id: str,
        tenant_slug: str,
        environment: str,
        aws_region: str,
    ) -> DeploymentRecord:
        """Create a new deployment record."""
        stack_name = f"{tenant_slug}-{environment}"

        with self.get_session() as session:
            existing = session.query(DeploymentRecord).filter_by(stack_name=stack_name).first()
            if existing:
                raise ValueError(f"Deployment {stack_name} already exists")

            record = DeploymentRecord(
                tenant_id=tenant_id,
                tenant_slug=tenant_slug,
                environment=environment,
                stack_name=stack_name,
                aws_region=aws_region,
                status=DeploymentStatus.PENDING,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_deployment(self, tenant_slug: str, environment: str) -> Optional[DeploymentRecord]:
        """Get deployment by tenant slug and environment."""
        stack_name = f"{tenant_slug}-{environment}"
        with self.get_session() as session:
            return session.query(DeploymentRecord).filter_by(stack_name=stack_name).first()

    def update_deployment_status(
        self,
        stack_name: str,
        status: DeploymentStatus,
        pulumi_deployment_id: Optional[str] = None,
        outputs: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[DeploymentRecord]:
        """Update deployment status."""
        with self.get_session() as session:
            record = session.query(DeploymentRecord).filter_by(stack_name=stack_name).first()
            if not record:
                return None

            record.status = status
            record.updated_at = datetime.utcnow()

            if pulumi_deployment_id:
                record.pulumi_deployment_id = pulumi_deployment_id
            if outputs:
                record.outputs = outputs
            if error_message:
                record.error_message = error_message

            session.commit()
            session.refresh(record)
            return record

    def list_deployments(self, tenant_slug: Optional[str] = None) -> list[DeploymentRecord]:
        """List deployments."""
        with self.get_session() as session:
            query = session.query(DeploymentRecord)
            if tenant_slug:
                query = query.filter_by(tenant_slug=tenant_slug)
            return query.all()

    def delete_deployment(self, stack_name: str) -> bool:
        """Delete deployment record."""
        with self.get_session() as session:
            record = session.query(DeploymentRecord).filter_by(stack_name=stack_name).first()
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True


# Global database instance
db = Database()
