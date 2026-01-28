# BYOC Platform

A multi-tenant BYOC (Bring Your Own Cloud) infrastructure deployment platform using Pulumi and FastAPI.

## Overview

This platform enables SaaS providers to deploy infrastructure into customer AWS accounts using cross-account role assumption. It provisions:

- **VPC and Networking**: VPC, subnets, NAT gateways, route tables
- **EKS Cluster**: Managed Kubernetes with Karpenter for autoscaling
- **Bootstrap Components**:
  - Karpenter (node autoscaling)
  - ArgoCD (GitOps)
  - Cert-manager (TLS certificates)
  - External Secrets Operator (secrets management)
  - Ingress NGINX (ingress controller)

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│   FastAPI       │     │           Pulumi Cloud                   │
│   Service       │────▶│   Pulumi Deployments (hosted workers)    │
│                 │     │   State Management                       │
└─────────────────┘     └──────────────────────────────────────────┘
                                          │
                                          ▼ AssumeRole
                              ┌───────────────────────┐
                              │  Customer AWS Account │
                              │  - VPC, EKS, IAM      │
                              │  - Bootstrap components│
                              └───────────────────────┘
```

## Prerequisites

- Python 3.11+
- Pulumi CLI installed
- Pulumi Cloud account
- AWS credentials (for your control plane account)

## Quick Start

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
export PULUMI_ACCESS_TOKEN="your-pulumi-access-token"
export PULUMI_ORG="your-pulumi-org"
export PULUMI_PROJECT="byoc-platform"
export GIT_REPO_URL="https://github.com/your-org/your-repo.git"
export GIT_REPO_BRANCH="main"
```

### 3. Run the API Locally

```bash
cd api
uvicorn main:app --reload --port 8000
```

### 4. Customer Onboarding

First, have your customer deploy the IAM role in their account:

```bash
aws cloudformation create-stack \
  --stack-name byoc-platform-role \
  --template-body file://templates/customer-iam-role.yaml \
  --parameters \
    ParameterKey=TrustedAccountId,ParameterValue=<YOUR_AWS_ACCOUNT_ID> \
    ParameterKey=ExternalId,ParameterValue=<UNIQUE_EXTERNAL_ID> \
  --capabilities CAPABILITY_NAMED_IAM
```

Then trigger the deployment via API:

```bash
curl -X POST http://localhost:8000/api/v1/customers/onboard \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "acme",
    "environment": "prod",
    "role_arn": "arn:aws:iam::123456789012:role/BYOCPlatformDeployRole",
    "external_id": "unique-external-id",
    "aws_region": "us-west-2"
  }'
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/customers/onboard` | Onboard a new customer |
| GET | `/api/v1/customers/{name}/{env}/status` | Get deployment status |
| GET | `/api/v1/customers/{name}/{env}/outputs` | Get infrastructure outputs |
| DELETE | `/api/v1/customers/{name}/{env}` | Offboard (destroy) customer |
| GET | `/api/v1/customers` | List all customers |

## Project Structure

```
.
├── __main__.py                 # Pulumi entry point
├── Pulumi.yaml                 # Pulumi project config
├── requirements.txt            # Python dependencies
├── api/
│   ├── main.py                 # FastAPI application
│   ├── models.py               # Pydantic models
│   ├── database.py             # SQLite for customer tracking
│   └── pulumi_deployments.py   # Pulumi Deployments API client
├── infra/
│   ├── config.py               # Customer configuration schema
│   ├── providers.py            # AWS/K8s provider setup
│   └── components/
│       ├── networking.py       # VPC, subnets, NAT
│       ├── eks.py              # EKS cluster
│       ├── iam.py              # IAM roles/policies
│       └── bootstrap.py        # Karpenter, ArgoCD, etc.
└── templates/
    └── customer-iam-role.yaml  # CloudFormation for customer IAM role
```

## Configuration

Stack configuration is set per customer via the API. Key settings:

| Config Key | Description | Default |
|------------|-------------|---------|
| `customerName` | Customer identifier | Required |
| `customerRoleArn` | IAM role ARN in customer account | Required |
| `externalId` | External ID for role assumption | Required |
| `awsRegion` | AWS region for deployment | us-east-1 |
| `vpcCidr` | VPC CIDR block | 10.0.0.0/16 |
| `eksVersion` | EKS Kubernetes version | 1.31 |
| `karpenterVersion` | Karpenter Helm chart version | 1.1.1 |
| `argocdVersion` | ArgoCD Helm chart version | 7.7.16 |

## Security

- Cross-account access uses IAM role assumption with external ID
- Secrets (external_id) are stored as Pulumi secrets
- Customer IAM role follows least-privilege principle
- All infrastructure is tagged for tracking

## Development

```bash
# Run type checking
pyright .

# Run linting
ruff check .

# Format code
ruff format .
```
