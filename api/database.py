"""SQLite database for tracking customer deployments."""

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


class CustomerDeploymentRecord(Base):
    """Database model for customer deployments."""

    __tablename__ = "customer_deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    stack_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    aws_region: Mapped[str] = mapped_column(String(20), nullable=False)
    role_arn: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus), nullable=False, default=DeploymentStatus.PENDING
    )
    pulumi_deployment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    outputs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Database:
    """Database connection and operations."""

    def __init__(self, database_url: str = "sqlite:///./byoc_platform.db"):
        """Initialize database connection.

        Args:
            database_url: SQLAlchemy database URL. Defaults to local SQLite.
        """
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def create_deployment(
        self,
        customer_name: str,
        environment: str,
        aws_region: str,
        role_arn: str,
    ) -> CustomerDeploymentRecord:
        """Create a new deployment record.

        Args:
            customer_name: Customer identifier
            environment: Environment name (dev/staging/prod)
            aws_region: AWS region for deployment
            role_arn: Customer's IAM role ARN

        Returns:
            Created deployment record
        """
        stack_name = f"{customer_name}-{environment}"

        with self.get_session() as session:
            # Check if deployment already exists
            existing = (
                session.query(CustomerDeploymentRecord).filter_by(stack_name=stack_name).first()
            )
            if existing:
                raise ValueError(f"Deployment {stack_name} already exists")

            record = CustomerDeploymentRecord(
                customer_name=customer_name,
                environment=environment,
                stack_name=stack_name,
                aws_region=aws_region,
                role_arn=role_arn,
                status=DeploymentStatus.PENDING,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_deployment(
        self,
        customer_name: str,
        environment: str,
    ) -> Optional[CustomerDeploymentRecord]:
        """Get deployment by customer name and environment.

        Args:
            customer_name: Customer identifier
            environment: Environment name

        Returns:
            Deployment record or None if not found
        """
        stack_name = f"{customer_name}-{environment}"
        with self.get_session() as session:
            return session.query(CustomerDeploymentRecord).filter_by(stack_name=stack_name).first()

    def get_deployment_by_stack(
        self,
        stack_name: str,
    ) -> Optional[CustomerDeploymentRecord]:
        """Get deployment by stack name.

        Args:
            stack_name: Pulumi stack name

        Returns:
            Deployment record or None if not found
        """
        with self.get_session() as session:
            return session.query(CustomerDeploymentRecord).filter_by(stack_name=stack_name).first()

    def update_deployment_status(
        self,
        stack_name: str,
        status: DeploymentStatus,
        pulumi_deployment_id: Optional[str] = None,
        outputs: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[CustomerDeploymentRecord]:
        """Update deployment status.

        Args:
            stack_name: Pulumi stack name
            status: New deployment status
            pulumi_deployment_id: Pulumi Deployments job ID
            outputs: JSON string of stack outputs
            error_message: Error message if failed

        Returns:
            Updated deployment record or None if not found
        """
        with self.get_session() as session:
            record = (
                session.query(CustomerDeploymentRecord).filter_by(stack_name=stack_name).first()
            )
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

    def list_deployments(
        self,
        customer_name: Optional[str] = None,
    ) -> list[CustomerDeploymentRecord]:
        """List all deployments, optionally filtered by customer.

        Args:
            customer_name: Optional customer filter

        Returns:
            List of deployment records
        """
        with self.get_session() as session:
            query = session.query(CustomerDeploymentRecord)
            if customer_name:
                query = query.filter_by(customer_name=customer_name)
            return query.all()

    def delete_deployment(self, stack_name: str) -> bool:
        """Delete a deployment record.

        Args:
            stack_name: Pulumi stack name

        Returns:
            True if deleted, False if not found
        """
        with self.get_session() as session:
            record = (
                session.query(CustomerDeploymentRecord).filter_by(stack_name=stack_name).first()
            )
            if not record:
                return False

            session.delete(record)
            session.commit()
            return True


# Global database instance
db = Database()
