"""EKS cluster bootstrap components.

Installs core platform components into the EKS cluster:
- Karpenter (node autoscaling)
- ArgoCD (GitOps)
- Cert-manager (TLS certificates)
- External Secrets Operator (secrets management)
- Ingress NGINX (ingress controller)
"""

import json

import pulumi
import pulumi_aws as aws
import pulumi_kubernetes as k8s

from infra.config import CustomerConfig


class ClusterBootstrap(pulumi.ComponentResource):
    """Bootstrap core components into EKS cluster."""

    def __init__(
        self,
        name: str,
        config: CustomerConfig,
        cluster_name: pulumi.Output[str],
        cluster_endpoint: pulumi.Output[str],
        cluster_ca_data: pulumi.Output[str],
        oidc_provider_arn: pulumi.Output[str],
        oidc_provider_url: pulumi.Output[str],
        node_role_arn: pulumi.Output[str],
        k8s_provider: k8s.Provider,
        aws_provider: aws.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:infrastructure:ClusterBootstrap", name, None, opts)

        # Get AWS account ID
        caller_identity = aws.get_caller_identity(opts=pulumi.InvokeOptions(provider=aws_provider))
        account_id = caller_identity.account_id

        # Install Karpenter
        karpenter = KarpenterInstall(
            f"{name}-karpenter",
            config=config,
            cluster_name=cluster_name,
            cluster_endpoint=cluster_endpoint,
            oidc_provider_arn=oidc_provider_arn,
            oidc_provider_url=oidc_provider_url,
            node_role_arn=node_role_arn,
            account_id=account_id,
            k8s_provider=k8s_provider,
            aws_provider=aws_provider,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Install Cert-manager (required before other components that use certificates)
        cert_manager = CertManagerInstall(
            f"{name}-cert-manager",
            version=config.cert_manager_version,
            k8s_provider=k8s_provider,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Install External Secrets Operator
        external_secrets = ExternalSecretsInstall(
            f"{name}-external-secrets",
            version=config.external_secrets_version,
            k8s_provider=k8s_provider,
            opts=pulumi.ResourceOptions(parent=self, depends_on=[cert_manager]),
        )

        # Install Ingress NGINX
        ingress_nginx = IngressNginxInstall(
            f"{name}-ingress-nginx",
            version=config.ingress_nginx_version,
            k8s_provider=k8s_provider,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Install ArgoCD
        argocd = ArgoCDInstall(
            f"{name}-argocd",
            version=config.argocd_version,
            repo_url=config.argocd_repo_url,
            k8s_provider=k8s_provider,
            opts=pulumi.ResourceOptions(parent=self, depends_on=[cert_manager, ingress_nginx]),
        )

        self.register_outputs(
            {
                "karpenter_namespace": karpenter.namespace,
                "argocd_namespace": argocd.namespace,
                "cert_manager_namespace": cert_manager.namespace,
                "external_secrets_namespace": external_secrets.namespace,
                "ingress_nginx_namespace": ingress_nginx.namespace,
            }
        )


class KarpenterInstall(pulumi.ComponentResource):
    """Install Karpenter for node autoscaling."""

    def __init__(
        self,
        name: str,
        config: CustomerConfig,
        cluster_name: pulumi.Output[str],
        cluster_endpoint: pulumi.Output[str],
        oidc_provider_arn: pulumi.Output[str],
        oidc_provider_url: pulumi.Output[str],
        node_role_arn: pulumi.Output[str],
        account_id: str,
        k8s_provider: k8s.Provider,
        aws_provider: aws.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:bootstrap:Karpenter", name, None, opts)

        k8s_opts = pulumi.ResourceOptions(parent=self, provider=k8s_provider)
        aws_opts = pulumi.ResourceOptions(parent=self, provider=aws_provider)

        # Create namespace
        self.ns = k8s.core.v1.Namespace(
            f"{name}-ns",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="karpenter"),
            opts=k8s_opts,
        )
        self.namespace = self.ns.metadata.name

        # Create IRSA role for Karpenter
        oidc_issuer = oidc_provider_url.apply(lambda url: url.replace("https://", ""))

        assume_role_policy = pulumi.Output.all(oidc_provider_arn, oidc_issuer).apply(
            lambda args: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Federated": args[0]},
                            "Action": "sts:AssumeRoleWithWebIdentity",
                            "Condition": {
                                "StringEquals": {
                                    f"{args[1]}:sub": "system:serviceaccount:karpenter:karpenter",
                                    f"{args[1]}:aud": "sts.amazonaws.com",
                                }
                            },
                        }
                    ],
                }
            )
        )

        self.karpenter_role = aws.iam.Role(
            f"{name}-role",
            assume_role_policy=assume_role_policy,
            opts=aws_opts,
        )

        # Attach Karpenter controller policy
        karpenter_policy = aws.iam.Policy(
            f"{name}-policy",
            policy=cluster_name.apply(
                lambda cn: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "Karpenter",
                                "Effect": "Allow",
                                "Action": [
                                    "ssm:GetParameter",
                                    "ec2:DescribeImages",
                                    "ec2:RunInstances",
                                    "ec2:DescribeSubnets",
                                    "ec2:DescribeSecurityGroups",
                                    "ec2:DescribeLaunchTemplates",
                                    "ec2:DescribeInstances",
                                    "ec2:DescribeInstanceTypes",
                                    "ec2:DescribeInstanceTypeOfferings",
                                    "ec2:DescribeAvailabilityZones",
                                    "ec2:DeleteLaunchTemplate",
                                    "ec2:CreateTags",
                                    "ec2:CreateLaunchTemplate",
                                    "ec2:CreateFleet",
                                    "ec2:DescribeSpotPriceHistory",
                                    "pricing:GetProducts",
                                ],
                                "Resource": "*",
                            },
                            {
                                "Sid": "ConditionalEC2Termination",
                                "Effect": "Allow",
                                "Action": "ec2:TerminateInstances",
                                "Resource": "*",
                                "Condition": {
                                    "StringLike": {"ec2:ResourceTag/karpenter.sh/nodepool": "*"}
                                },
                            },
                            {
                                "Sid": "PassNodeIAMRole",
                                "Effect": "Allow",
                                "Action": "iam:PassRole",
                                "Resource": "*",
                                "Condition": {
                                    "StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}
                                },
                            },
                            {
                                "Sid": "EKSClusterEndpointLookup",
                                "Effect": "Allow",
                                "Action": ["eks:DescribeCluster"],
                                "Resource": f"arn:aws:eks:*:{account_id}:cluster/{cn}",
                            },
                            {
                                "Sid": "AllowScopedInstanceProfileCreationActions",
                                "Effect": "Allow",
                                "Action": ["iam:CreateInstanceProfile"],
                                "Resource": "*",
                                "Condition": {
                                    "StringEquals": {
                                        f"aws:RequestTag/kubernetes.io/cluster/{cn}": "owned"
                                    },
                                    "StringLike": {
                                        "aws:RequestTag/karpenter.k8s.aws/ec2nodeclass": "*"
                                    },
                                },
                            },
                            {
                                "Sid": "AllowScopedInstanceProfileTagActions",
                                "Effect": "Allow",
                                "Action": ["iam:TagInstanceProfile"],
                                "Resource": "*",
                                "Condition": {
                                    "StringEquals": {
                                        f"aws:ResourceTag/kubernetes.io/cluster/{cn}": "owned",
                                        f"aws:RequestTag/kubernetes.io/cluster/{cn}": "owned",
                                    },
                                    "StringLike": {
                                        "aws:ResourceTag/karpenter.k8s.aws/ec2nodeclass": "*",
                                        "aws:RequestTag/karpenter.k8s.aws/ec2nodeclass": "*",
                                    },
                                },
                            },
                            {
                                "Sid": "AllowScopedInstanceProfileActions",
                                "Effect": "Allow",
                                "Action": [
                                    "iam:AddRoleToInstanceProfile",
                                    "iam:RemoveRoleFromInstanceProfile",
                                    "iam:DeleteInstanceProfile",
                                ],
                                "Resource": "*",
                                "Condition": {
                                    "StringEquals": {
                                        f"aws:ResourceTag/kubernetes.io/cluster/{cn}": "owned"
                                    },
                                    "StringLike": {
                                        "aws:ResourceTag/karpenter.k8s.aws/ec2nodeclass": "*"
                                    },
                                },
                            },
                            {
                                "Sid": "AllowInstanceProfileReadActions",
                                "Effect": "Allow",
                                "Action": "iam:GetInstanceProfile",
                                "Resource": "*",
                            },
                        ],
                    }
                )
            ),
            opts=aws_opts,
        )

        aws.iam.RolePolicyAttachment(
            f"{name}-policy-attachment",
            role=self.karpenter_role.name,
            policy_arn=karpenter_policy.arn,
            opts=aws_opts,
        )

        # Install Karpenter Helm chart
        self.release = k8s.helm.v3.Release(
            f"{name}-release",
            chart="karpenter",
            version=config.karpenter_version,
            namespace=self.namespace,
            repository_opts=k8s.helm.v3.RepositoryOptsArgs(
                repo="oci://public.ecr.aws/karpenter",
            ),
            values={
                "settings": {
                    "clusterName": cluster_name,
                    "clusterEndpoint": cluster_endpoint,
                    "interruptionQueue": "",  # Optional SQS queue for spot interruption
                },
                "serviceAccount": {
                    "annotations": {
                        "eks.amazonaws.com/role-arn": self.karpenter_role.arn,
                    },
                },
                "controller": {
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "256Mi"},
                        "limits": {"cpu": "1", "memory": "1Gi"},
                    },
                },
            },
            opts=pulumi.ResourceOptions(
                parent=self, provider=k8s_provider, depends_on=[self.ns, self.karpenter_role]
            ),
        )

        # Create default NodePool and EC2NodeClass
        self.node_pool = k8s.apiextensions.CustomResource(
            f"{name}-default-nodepool",
            api_version="karpenter.sh/v1",
            kind="NodePool",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="default"),
            spec={
                "template": {
                    "spec": {
                        "requirements": [
                            {"key": "kubernetes.io/arch", "operator": "In", "values": ["amd64"]},
                            {
                                "key": "karpenter.sh/capacity-type",
                                "operator": "In",
                                "values": ["spot", "on-demand"],
                            },
                            {
                                "key": "karpenter.k8s.aws/instance-category",
                                "operator": "In",
                                "values": ["c", "m", "r"],
                            },
                            {
                                "key": "karpenter.k8s.aws/instance-generation",
                                "operator": "Gt",
                                "values": ["5"],
                            },
                        ],
                        "nodeClassRef": {
                            "group": "karpenter.k8s.aws",
                            "kind": "EC2NodeClass",
                            "name": "default",
                        },
                        "expireAfter": "720h",  # 30 days
                    },
                },
                "limits": {"cpu": "1000", "memory": "1000Gi"},
                "disruption": {
                    "consolidationPolicy": "WhenEmptyOrUnderutilized",
                    "consolidateAfter": "1m",
                },
            },
            opts=pulumi.ResourceOptions(
                parent=self, provider=k8s_provider, depends_on=[self.release]
            ),
        )

        self.ec2_node_class = k8s.apiextensions.CustomResource(
            f"{name}-default-ec2nodeclass",
            api_version="karpenter.k8s.aws/v1",
            kind="EC2NodeClass",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="default"),
            spec={
                "amiSelectorTerms": [{"alias": "al2023@latest"}],
                "role": node_role_arn.apply(lambda arn: arn.split("/")[-1]),
                "subnetSelectorTerms": [{"tags": {"karpenter.sh/discovery": config.customer_name}}],
                "securityGroupSelectorTerms": [
                    {"tags": {"karpenter.sh/discovery": config.customer_name}}
                ],
                "tags": {
                    "karpenter.sh/discovery": config.customer_name,
                    "ManagedBy": "Karpenter",
                },
            },
            opts=pulumi.ResourceOptions(
                parent=self, provider=k8s_provider, depends_on=[self.release]
            ),
        )

        self.register_outputs({"namespace": self.namespace, "role_arn": self.karpenter_role.arn})


class CertManagerInstall(pulumi.ComponentResource):
    """Install cert-manager for TLS certificate management."""

    def __init__(
        self,
        name: str,
        version: str,
        k8s_provider: k8s.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:bootstrap:CertManager", name, None, opts)

        k8s_opts = pulumi.ResourceOptions(parent=self, provider=k8s_provider)

        # Create namespace
        self.ns = k8s.core.v1.Namespace(
            f"{name}-ns",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="cert-manager"),
            opts=k8s_opts,
        )
        self.namespace = self.ns.metadata.name

        # Install cert-manager Helm chart
        self.release = k8s.helm.v3.Release(
            f"{name}-release",
            chart="cert-manager",
            version=version,
            namespace=self.namespace,
            repository_opts=k8s.helm.v3.RepositoryOptsArgs(
                repo="https://charts.jetstack.io",
            ),
            values={
                "installCRDs": True,
                "resources": {
                    "requests": {"cpu": "50m", "memory": "64Mi"},
                    "limits": {"cpu": "200m", "memory": "256Mi"},
                },
            },
            opts=pulumi.ResourceOptions(parent=self, provider=k8s_provider, depends_on=[self.ns]),
        )

        self.register_outputs({"namespace": self.namespace})


class ExternalSecretsInstall(pulumi.ComponentResource):
    """Install External Secrets Operator for secrets management."""

    def __init__(
        self,
        name: str,
        version: str,
        k8s_provider: k8s.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:bootstrap:ExternalSecrets", name, None, opts)

        k8s_opts = pulumi.ResourceOptions(parent=self, provider=k8s_provider)

        # Create namespace
        self.ns = k8s.core.v1.Namespace(
            f"{name}-ns",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="external-secrets"),
            opts=k8s_opts,
        )
        self.namespace = self.ns.metadata.name

        # Install External Secrets Operator Helm chart
        self.release = k8s.helm.v3.Release(
            f"{name}-release",
            chart="external-secrets",
            version=version,
            namespace=self.namespace,
            repository_opts=k8s.helm.v3.RepositoryOptsArgs(
                repo="https://charts.external-secrets.io",
            ),
            values={
                "installCRDs": True,
                "resources": {
                    "requests": {"cpu": "50m", "memory": "64Mi"},
                    "limits": {"cpu": "200m", "memory": "256Mi"},
                },
            },
            opts=pulumi.ResourceOptions(parent=self, provider=k8s_provider, depends_on=[self.ns]),
        )

        self.register_outputs({"namespace": self.namespace})


class IngressNginxInstall(pulumi.ComponentResource):
    """Install NGINX Ingress Controller."""

    def __init__(
        self,
        name: str,
        version: str,
        k8s_provider: k8s.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:bootstrap:IngressNginx", name, None, opts)

        k8s_opts = pulumi.ResourceOptions(parent=self, provider=k8s_provider)

        # Create namespace
        self.ns = k8s.core.v1.Namespace(
            f"{name}-ns",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="ingress-nginx"),
            opts=k8s_opts,
        )
        self.namespace = self.ns.metadata.name

        # Install ingress-nginx Helm chart
        self.release = k8s.helm.v3.Release(
            f"{name}-release",
            chart="ingress-nginx",
            version=version,
            namespace=self.namespace,
            repository_opts=k8s.helm.v3.RepositoryOptsArgs(
                repo="https://kubernetes.github.io/ingress-nginx",
            ),
            values={
                "controller": {
                    "service": {
                        "type": "LoadBalancer",
                        "annotations": {
                            "service.beta.kubernetes.io/aws-load-balancer-type": "nlb",
                            "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing",
                        },
                    },
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "500m", "memory": "512Mi"},
                    },
                    "metrics": {"enabled": True},
                },
            },
            opts=pulumi.ResourceOptions(parent=self, provider=k8s_provider, depends_on=[self.ns]),
        )

        self.register_outputs({"namespace": self.namespace})


class ArgoCDInstall(pulumi.ComponentResource):
    """Install ArgoCD for GitOps."""

    def __init__(
        self,
        name: str,
        version: str,
        repo_url: str,
        k8s_provider: k8s.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:bootstrap:ArgoCD", name, None, opts)

        k8s_opts = pulumi.ResourceOptions(parent=self, provider=k8s_provider)

        # Create namespace
        self.ns = k8s.core.v1.Namespace(
            f"{name}-ns",
            metadata=k8s.meta.v1.ObjectMetaArgs(name="argocd"),
            opts=k8s_opts,
        )
        self.namespace = self.ns.metadata.name

        # Build values with optional repo configuration
        values: dict = {
            "server": {
                "service": {"type": "ClusterIP"},
                "resources": {
                    "requests": {"cpu": "50m", "memory": "128Mi"},
                    "limits": {"cpu": "500m", "memory": "512Mi"},
                },
            },
            "controller": {
                "resources": {
                    "requests": {"cpu": "100m", "memory": "256Mi"},
                    "limits": {"cpu": "1", "memory": "1Gi"},
                },
            },
            "repoServer": {
                "resources": {
                    "requests": {"cpu": "50m", "memory": "128Mi"},
                    "limits": {"cpu": "500m", "memory": "512Mi"},
                },
            },
            "applicationSet": {
                "resources": {
                    "requests": {"cpu": "50m", "memory": "64Mi"},
                    "limits": {"cpu": "200m", "memory": "256Mi"},
                },
            },
        }

        # Add repository configuration if provided
        if repo_url:
            values["configs"] = {
                "repositories": {
                    "app-repo": {
                        "url": repo_url,
                        "type": "git",
                    },
                },
            }

        # Install ArgoCD Helm chart
        self.release = k8s.helm.v3.Release(
            f"{name}-release",
            chart="argo-cd",
            version=version,
            namespace=self.namespace,
            repository_opts=k8s.helm.v3.RepositoryOptsArgs(
                repo="https://argoproj.github.io/argo-helm",
            ),
            values=values,
            opts=pulumi.ResourceOptions(parent=self, provider=k8s_provider, depends_on=[self.ns]),
        )

        self.register_outputs({"namespace": self.namespace})
