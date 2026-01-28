"""BYOC Platform - Main entry point for Pulumi infrastructure deployment."""

import pulumi

from infra.components.bootstrap import ClusterBootstrap
from infra.components.eks import EksCluster
from infra.components.iam import IamRoles
from infra.components.networking import Networking
from infra.config import load_customer_config
from infra.providers import create_customer_aws_provider, create_k8s_provider

# Load customer configuration from stack config
config = load_customer_config()

# Create AWS provider that assumes role in customer's account
aws_provider = create_customer_aws_provider(config)

# 1. Networking (VPC, subnets, NAT gateways)
networking = Networking(
    name=config.customer_name,
    vpc_cidr=config.vpc_cidr,
    availability_zones=config.availability_zones,
    provider=aws_provider,
)

# 2. IAM roles for EKS and IRSA
iam = IamRoles(
    name=config.customer_name,
    provider=aws_provider,
    opts=pulumi.ResourceOptions(depends_on=[networking]),
)

# 3. EKS cluster with Karpenter for autoscaling
eks_cluster = EksCluster(
    name=config.customer_name,
    vpc_id=networking.vpc_id,
    private_subnet_ids=networking.private_subnet_ids,
    public_subnet_ids=networking.public_subnet_ids,
    eks_version=config.eks_version,
    provider=aws_provider,
    opts=pulumi.ResourceOptions(depends_on=[networking, iam]),
)

# 4. Kubernetes provider from EKS kubeconfig
k8s_provider = create_k8s_provider(
    name=config.customer_name,
    kubeconfig=eks_cluster.kubeconfig,
    parent=eks_cluster,
)

# 5. Bootstrap components (Karpenter, ArgoCD, Cert-manager, External Secrets, Ingress)
bootstrap = ClusterBootstrap(
    name=config.customer_name,
    config=config,
    cluster_name=eks_cluster.cluster_name,
    cluster_endpoint=eks_cluster.cluster_endpoint,
    cluster_ca_data=eks_cluster.cluster_ca_data,
    oidc_provider_arn=eks_cluster.oidc_provider_arn,
    oidc_provider_url=eks_cluster.oidc_provider_url,
    node_role_arn=eks_cluster.node_role_arn,
    k8s_provider=k8s_provider,
    aws_provider=aws_provider,
    opts=pulumi.ResourceOptions(depends_on=[eks_cluster]),
)

# Exports
pulumi.export("vpc_id", networking.vpc_id)
pulumi.export("private_subnet_ids", networking.private_subnet_ids)
pulumi.export("public_subnet_ids", networking.public_subnet_ids)
pulumi.export("eks_cluster_name", eks_cluster.cluster_name)
pulumi.export("eks_cluster_endpoint", eks_cluster.cluster_endpoint)
pulumi.export("kubeconfig", pulumi.Output.secret(eks_cluster.kubeconfig))
