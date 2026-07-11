from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_msk as msk,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam
)
from constructs import Construct

class IotHackathonStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. Create VPC
        vpc = ec2.Vpc(self, "IotVpc", max_azs=2)

        # 2. Secret for PostgreSQL
        db_secret = secretsmanager.Secret(self, "PostgresCredentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"postgres"}',
                generate_string_key="password",
                exclude_characters='"@/\\'
            )
        )

        # 3. EC2 Security Group
        sg_ec2 = ec2.SecurityGroup(self, "PostgresSg", 
            vpc=vpc,
            description="Security group for PostgreSQL EC2 instance"
        )
        sg_ec2.add_ingress_rule(
            ec2.Peer.ipv4(vpc.vpc_cidr_block), 
            ec2.Port.tcp(5432), 
            "Allow PostgreSQL traffic from VPC"
        )

        # 4. Create IAM Role for EC2
        ec2_role = iam.Role(self, "EC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )

        # 5. Bastion Host & Private EC2
        bastion = ec2.BastionHostLinux(self, "BastionHost", 
            vpc=vpc,
            instance_type=ec2.InstanceType("t3.micro")
        )
        
        postgres_instance = ec2.Instance(self, "PostgresInstance",
            vpc=vpc,
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=ec2.MachineImage.latest_amazon_linux2(),
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_group=sg_ec2,
            role=ec2_role
        )

        # 6. MSK Security Group (remove duplicate)
        sg_msk = ec2.SecurityGroup(self, "MskSg", 
            vpc=vpc,
            description="Security group for MSK cluster"
        )
        sg_msk.add_ingress_rule(
            sg_msk, 
            ec2.Port.all_traffic(), 
            "Allow internal MSK communication"
        )
        # Allow EC2 to communicate with MSK
        sg_msk.add_ingress_rule(
            sg_ec2,
            ec2.Port.tcp(9092),
            "Allow EC2 to access Kafka"
        )
        sg_msk.add_ingress_rule(
            sg_ec2,
            ec2.Port.tcp(9094),
            "Allow EC2 to access Kafka TLS"
        )

        # 7. MSK Cluster (Kafka)
        msk_cluster = msk.CfnCluster(self, "MskCluster",
            cluster_name="iot-kafka-cluster",
            kafka_version="3.8.x",
            number_of_broker_nodes=2, 
            broker_node_group_info=msk.CfnCluster.BrokerNodeGroupInfoProperty(
                client_subnets=[subnet.subnet_id for subnet in vpc.private_subnets],
                instance_type="kafka.m5.large",
                security_groups=[sg_msk.security_group_id]
            ),
            encryption_info=msk.CfnCluster.EncryptionInfoProperty(
                encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                    client_broker="TLS"
                )
            )
        )

        # 8. Output useful information
        from aws_cdk import CfnOutput
        CfnOutput(self, "PostgresSecretArn", value=db_secret.secret_arn)
        CfnOutput(self, "VpcId", value=vpc.vpc_id)
        CfnOutput(self, "BastionHostId", value=bastion.instance_id if hasattr(bastion, 'instance_id') else "check-console")