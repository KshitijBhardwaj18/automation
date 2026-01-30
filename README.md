# BYOC Platform

Multi-tenant BYOC (Bring Your Own Cloud) infrastructure deployment platform using Pulumi and FastAPI.

## Overview

Deploy infrastructure into tenant AWS accounts using cross-account role assumption:

- **VPC and Networking**: VPC, subnets, NAT gateway, route tables
- **EKS Cluster**: Managed Kubernetes (auto or managed node groups)
- **Bootstrap Components**: Karpenter, ArgoCD, Cert-manager, External Secrets, Ingress NGINX

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│   FastAPI       │     │           Pulumi Cloud                   │
│   Service       │────▶│   Pulumi Deployments (hosted workers)    │
└─────────────────┘     └──────────────────────────────────────────┘
                                          │
                                          ▼ AssumeRole
                              ┌───────────────────────┐
                              │  Tenant AWS Account   │
                              │  - VPC, EKS, IAM      │
                              └───────────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Run the API

```bash
uvicorn api.main:app --reload --port 8000
```

### 4. Create a Tenant

```bash
# Create tenant (generates external_id)
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corporation",
    "slug": "acme",
    "aws_account_id": "123456789012"
  }'
```

Save the `external_id` from the response - it's only shown once.

### 5. Set Up IAM Role in Tenant Account

Have the tenant create the IAM role using the template:

```bash
aws cloudformation create-stack \
  --stack-name byoc-platform-role \
  --template-body file://templates/customer-iam-role.yaml \
  --parameters \
    ParameterKey=TrustedAccountId,ParameterValue=<YOUR_PLATFORM_ACCOUNT_ID> \
    ParameterKey=ExternalId,ParameterValue=<EXTERNAL_ID_FROM_STEP_4> \
  --capabilities CAPABILITY_NAMED_IAM
```

### 6. Save Config and Deploy

```bash
# Save environment config
curl -X POST http://localhost:8000/api/v1/tenants/acme/environments/dev/config \
  -H "Content-Type: application/json" \
  -d '{
    "eks_mode": "managed",
    "node_group_config": {"desired_size": 2}
  }'

# Deploy
curl -X POST http://localhost:8000/api/v1/tenants/acme/environments/dev/deploy \
  -H "Content-Type: application/json" -d '{}'

# Check status
curl http://localhost:8000/api/v1/tenants/acme/environments/dev/status
```

## API Endpoints

### Tenants
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tenants` | Create tenant |
| GET | `/api/v1/tenants` | List tenants |
| GET | `/api/v1/tenants/{slug}` | Get tenant |
| DELETE | `/api/v1/tenants/{slug}` | Delete tenant |

### Config
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tenants/{slug}/environments/{env}/config` | Save config |
| GET | `/api/v1/tenants/{slug}/environments/{env}/config` | Get config |
| DELETE | `/api/v1/tenants/{slug}/environments/{env}/config` | Delete config |

### Deployment
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/tenants/{slug}/environments/{env}/deploy` | Deploy |
| GET | `/api/v1/tenants/{slug}/environments/{env}/status` | Get status |
| DELETE | `/api/v1/tenants/{slug}/environments/{env}` | Destroy |

## Project Structure

```
.
├── __main__.py              # Pulumi entry point
├── Pulumi.yaml              # Pulumi project config
├── requirements.txt         # Python dependencies
├── api/
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic models
│   ├── database.py          # SQLite database
│   ├── config_store.py      # Config file storage
│   ├── pulumi_deployments.py # Pulumi API client
│   └── settings.py          # App settings
├── infra/
│   ├── config.py            # Configuration schema
│   ├── providers.py         # AWS/K8s providers
│   └── components/
│       ├── networking.py    # VPC, subnets, NAT
│       ├── eks.py           # EKS cluster
│       ├── iam.py           # IAM roles/policies
│       └── bootstrap.py     # Helm charts
└── templates/
    └── customer-iam-role.yaml  # IAM role template
```

## Data Model

- **Tenant**: Organization with AWS account
  - `id`: UUID (internal)
  - `slug`: Unique identifier (used in stack names)
  - `name`: Display name
  - `external_id`: Generated secret for role assumption

- **Stack naming**: `{tenant_slug}-{environment}` (e.g., `acme-dev`)

## Development

```bash
# Type checking
pyright .

# Linting
ruff check .

# Format
ruff format .
```
