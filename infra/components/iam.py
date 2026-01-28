"""IAM roles and policies for EKS and IRSA."""

import pulumi
import pulumi_aws as aws


class IamRoles(pulumi.ComponentResource):
    """IAM roles and policies for EKS cluster components.

    Creates base IAM roles. IRSA roles for specific components (Karpenter,
    External Secrets, etc.) are created in the bootstrap module where they
    have access to the OIDC provider information.
    """

    def __init__(
        self,
        name: str,
        provider: aws.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:infrastructure:IamRoles", name, None, opts)

        child_opts = pulumi.ResourceOptions(parent=self, provider=provider)

        # Get current AWS account ID and region
        caller_identity = aws.get_caller_identity(opts=pulumi.InvokeOptions(provider=provider))
        self.account_id = caller_identity.account_id

        region = aws.get_region(opts=pulumi.InvokeOptions(provider=provider))
        self.region = region.name

        # Create a policy for EKS cluster autoscaler (used by Karpenter)
        self.cluster_autoscaler_policy = aws.iam.Policy(
            f"{name}-cluster-autoscaler-policy",
            description="Policy for Karpenter to manage EC2 instances",
            policy=pulumi.Output.json_dumps(
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
                            "Resource": f"arn:aws:iam::{self.account_id}:role/*",
                            "Condition": {
                                "StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}
                            },
                        },
                        {
                            "Sid": "EKSClusterEndpointLookup",
                            "Effect": "Allow",
                            "Action": ["eks:DescribeCluster"],
                            "Resource": f"arn:aws:eks:{self.region}:{self.account_id}:cluster/*",
                        },
                        {
                            "Sid": "AllowScopedInstanceProfileCreationActions",
                            "Effect": "Allow",
                            "Action": ["iam:CreateInstanceProfile"],
                            "Resource": "*",
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/kubernetes.io/cluster/${CLUSTER_NAME}": "owned",
                                    "aws:RequestTag/topology.kubernetes.io/region": self.region,
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
                                    "aws:ResourceTag/kubernetes.io/cluster/${CLUSTER_NAME}": "owned",
                                    "aws:ResourceTag/topology.kubernetes.io/region": self.region,
                                    "aws:RequestTag/kubernetes.io/cluster/${CLUSTER_NAME}": "owned",
                                    "aws:RequestTag/topology.kubernetes.io/region": self.region,
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
                                    "aws:ResourceTag/kubernetes.io/cluster/${CLUSTER_NAME}": "owned",
                                    "aws:ResourceTag/topology.kubernetes.io/region": self.region,
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
            ),
            opts=child_opts,
        )

        self.register_outputs(
            {
                "account_id": self.account_id,
                "region": self.region,
                "cluster_autoscaler_policy_arn": self.cluster_autoscaler_policy.arn,
            }
        )
