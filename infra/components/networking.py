"""VPC and networking infrastructure for customer deployments."""

import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx


class Networking(pulumi.ComponentResource):
    """VPC and networking infrastructure for a customer.

    Creates:
    - VPC with specified CIDR
    - Public subnets (for load balancers)
    - Private subnets (for EKS nodes)
    - NAT gateways (one per AZ for high availability)
    - Internet gateway
    - Route tables
    """

    def __init__(
        self,
        name: str,
        vpc_cidr: str,
        availability_zones: list[str],
        provider: aws.Provider,
        opts: pulumi.ResourceOptions | None = None,
    ):
        super().__init__("byoc:infrastructure:Networking", name, None, opts)

        child_opts = pulumi.ResourceOptions(parent=self, provider=provider)

        # Create VPC using awsx for simplified setup
        # Using SINGLE NAT gateway to reduce costs and EIP usage
        # For production, change to ONE_PER_AZ for high availability
        self.vpc = awsx.ec2.Vpc(
            f"{name}-vpc",
            cidr_block=vpc_cidr,
            availability_zone_names=availability_zones,
            nat_gateways=awsx.ec2.NatGatewayConfigurationArgs(
                strategy=awsx.ec2.NatGatewayStrategy.SINGLE,
            ),
            subnet_strategy=awsx.ec2.SubnetAllocationStrategy.AUTO,
            subnet_specs=[
                # Public subnets for load balancers
                awsx.ec2.SubnetSpecArgs(
                    type=awsx.ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                    tags={
                        "kubernetes.io/role/elb": "1",
                        "karpenter.sh/discovery": name,
                    },
                ),
                # Private subnets for EKS nodes
                awsx.ec2.SubnetSpecArgs(
                    type=awsx.ec2.SubnetType.PRIVATE,
                    cidr_mask=20,
                    tags={
                        "kubernetes.io/role/internal-elb": "1",
                        "karpenter.sh/discovery": name,
                    },
                ),
            ],
            tags={
                "Name": f"{name}-vpc",
            },
            opts=child_opts,
        )

        # Export outputs
        self.vpc_id = self.vpc.vpc_id
        self.private_subnet_ids = self.vpc.private_subnet_ids
        self.public_subnet_ids = self.vpc.public_subnet_ids

        self.register_outputs(
            {
                "vpc_id": self.vpc_id,
                "private_subnet_ids": self.private_subnet_ids,
                "public_subnet_ids": self.public_subnet_ids,
            }
        )
