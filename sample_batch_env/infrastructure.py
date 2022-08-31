# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import aws_cdk as core
from constructs import Construct
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam


STACK_PREFIX = "sample-batch-env"

# Network
VPC_ID = STACK_PREFIX + "-vpc-id"
SECURITY_GROUP_ID = STACK_PREFIX + "-sg-id"
SECURITY_GROUP_NAME = STACK_PREFIX + "-sg"

# Roles
BATCH_SERVICE_ROLE_ID = STACK_PREFIX + "-batch-service-role-id"
BATCH_SERVICE_ROLE_NAME = STACK_PREFIX + "-batch-service-role"

ECS_TASK_EXECUTION_ROLE_ID = STACK_PREFIX + "-ecs-task-execution-role-id"
ECS_TASK_EXECUTION_ROLE_NAME = STACK_PREFIX + "-ecs-task-execution-role"

# Compute Environment
COMPUTE_TYPE = "FARGATE"
COMPUTE_ENVIRONMENT_ID = STACK_PREFIX + "-" + COMPUTE_TYPE.lower() + "-compute-environment-id"
COMPUTE_ENVIRONMENT_NAME = STACK_PREFIX + "-" + COMPUTE_TYPE.lower() + "-compute-environment"
COMPUTE_MAX_VCPUS = 256

# Job Queue
JOB_QUEUE_ID = STACK_PREFIX + "-job-queue-id"
JOB_QUEUE_NAME = STACK_PREFIX + "-job-queue"

# Job Definition
JOB_DEFINITION_ID = STACK_PREFIX + "-job-definition-id"
JOB_DEFINITION_NAME = STACK_PREFIX + "-job-definition"
CONTAINER_IMAGE = "amazonlinux"

class AwsCdkFargateBatchStack(core.Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        # VPC & Security Group
        vpc = ec2.Vpc(scope=self, id=VPC_ID, max_azs=3)

        sg = ec2.SecurityGroup(self, SECURITY_GROUP_ID, 
            vpc=vpc, 
            security_group_name=SECURITY_GROUP_NAME
        )

        # IAM Roles and Permissions
        batch_service_role = iam.Role(self, BATCH_SERVICE_ROLE_ID,
            role_name=BATCH_SERVICE_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("batch.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSBatchServiceRole")
            ]
        )
        
        ecs_task_execution_role = iam.Role(self, ECS_TASK_EXECUTION_ROLE_ID,
            role_name=ECS_TASK_EXECUTION_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")
            ]
        )
        
         # Compute Environment
        compute_environment = batch.CfnComputeEnvironment(self, COMPUTE_ENVIRONMENT_ID,
            compute_environment_name=COMPUTE_ENVIRONMENT_NAME,
            type="MANAGED",
            service_role=batch_service_role.role_arn,
            compute_resources={
                "type": COMPUTE_TYPE,
                "maxvCpus": COMPUTE_MAX_VCPUS,
                "subnets": [subnet.subnet_id for subnet in vpc.public_subnets],
                "securityGroupIds": [sg.security_group_id]
            }
        )
        
        # Job Queue
        job_queue = batch.CfnJobQueue(self, JOB_QUEUE_ID,
            job_queue_name=JOB_QUEUE_NAME,
            priority=1,
            compute_environment_order=[
                {
                    "order": 1, 
                    "computeEnvironment": compute_environment.compute_environment_name
                }
            ]
        )
        job_queue.add_depends_on(compute_environment)
        
        # Job Definition
        job_definition = batch.CfnJobDefinition(self, JOB_DEFINITION_ID,
            job_definition_name=JOB_DEFINITION_NAME,
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties={
                "image": CONTAINER_IMAGE,
                "resourceRequirements": [{"type": "VCPU","value": "1"}, {"type": "MEMORY","value": "2048"}],
                "command": ["echo","hello world"],
                "executionRoleArn": ecs_task_execution_role.role_arn,
                "networkConfiguration": {"assignPublicIp": "ENABLED"}
            }
        )