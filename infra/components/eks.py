"""EKS cluster infrastructure for customer deployments."""

import json

import pulumi
import pulumi_aws as aws
import pulumi_eks as eks


class EksCluster(pulumi.ComponentResource):
    """EKS cluster with Karpenter-ready configuration.

    Creates:
    - EKS cluster with specified Kubernetes version
    - Initial managed node group (for system workloads and Karpenter)
    - OIDC provider for IRSA (IAM Roles for Service Accounts)
    - Cluster security group
    - Node IAM role

    Karpenter will be installed separately and will manage additional nodes.
    """

    def __init__(
        self,
        name: str,
        vpc_id: pulumi.Output[str],
        private_subnet_ids: pulumi.Output,
        public_subnet_ids: pulumi.Output,
        eks_version: str,
        provider: aws.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:infrastructure:EksCluster", name, None, opts)

        child_opts = pulumi.ResourceOptions(parent=self, provider=provider)

        # Create EKS cluster using pulumi-eks component
        # This creates a minimal initial node group for system workloads
        # Karpenter will handle application workload scaling
        self.cluster = eks.Cluster(
            f"{name}-cluster",
            vpc_id=vpc_id,
            private_subnet_ids=private_subnet_ids,
            public_subnet_ids=public_subnet_ids,
            version=eks_version,
            # Initial node group for system workloads (Karpenter, CoreDNS, etc.)
            # Karpenter will manage additional capacity
            instance_type="m6i.large",
            desired_capacity=2,
            min_size=2,
            max_size=3,
            node_associate_public_ip_address=False,
            # Enable private and public endpoint access
            endpoint_private_access=True,
            endpoint_public_access=True,
            # Enable cluster logging
            enabled_cluster_log_types=[
                "api",
                "audit",
                "authenticator",
                "controllerManager",
                "scheduler",
            ],
            # Create OIDC provider for IRSA
            create_oidc_provider=True,
            # Tags for Karpenter discovery
            tags={
                "Name": f"{name}-cluster",
                "karpenter.sh/discovery": name,
            },
            opts=child_opts,
        )

        # Get the node role ARN for Karpenter configuration
        self.node_role_arn = self.cluster.instance_roles.apply(
            lambda roles: roles[0].arn if roles else ""
        )

        # Export outputs
        self.cluster_name = self.cluster.eks_cluster.name
        self.cluster_endpoint = self.cluster.eks_cluster.endpoint
        self.cluster_ca_data = self.cluster.eks_cluster.certificate_authority.apply(
            lambda ca: ca.data if ca else ""
        )
        self.kubeconfig = self.cluster.kubeconfig.apply(lambda kc: json.dumps(kc))
        self.oidc_provider_arn = self.cluster.core.oidc_provider.arn
        self.oidc_provider_url = self.cluster.core.oidc_provider.url

        self.register_outputs(
            {
                "cluster_name": self.cluster_name,
                "cluster_endpoint": self.cluster_endpoint,
                "kubeconfig": self.kubeconfig,
                "oidc_provider_arn": self.oidc_provider_arn,
                "oidc_provider_url": self.oidc_provider_url,
                "node_role_arn": self.node_role_arn,
            }
        )
