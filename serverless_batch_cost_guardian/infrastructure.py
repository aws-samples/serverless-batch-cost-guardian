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
from aws_cdk import aws_lambda as lambda_ # lambda is system reserved name
from aws_cdk import aws_iam as iam
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_events as aws_events
from aws_cdk import aws_events_targets as aws_targets
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks

GUARDIAN_STACK_PREFIX = "serverless-batch-cost-guardian"

class ServerlessBatchCostGuardianStack(core.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Resources defined in similar order (descending) of architecture diagram
        
        ###
        
        # Stop New Jobs Lambda IAM Role
        stop_new_jobs_lambda_role = iam.Role(scope=self, id='stop-new-jobs-lambda-iam-role',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name='stop-new-jobs-lambda-iam-role',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole') 
            ])

        # Input parameters Batch Compute Env + Job Queue for Stop New Jobs Lambda: 
        batch_compute_env_name = core.CfnParameter(self, 'batchComputeEnvName',
          type='String',
          description='Name of Batch Compute Environment'
        )
        
        batch_job_queue_name = core.CfnParameter(self, 'batchJobQueueName',
          type='String',
          description='Name of Batch Job Queue'
        )
        
        account_id = self.account
        region = self.region
        
        batch_compute_env_arn = 'arn:aws:batch:' + str(region) + ':' + str(account_id) + ':compute-environment/' + batch_compute_env_name.value_as_string
        batch_job_queue_arn = 'arn:aws:batch:' + str(region) + ':' + str(account_id) + ':job-queue/' + batch_job_queue_name.value_as_string
        
        # Add customer managed policy to allow Lambda access to Batch update CE and Queue
        stop_new_jobs_lambda_role.attach_inline_policy(iam.Policy(self, "batch-update-ce-queue-policy",
            statements=[iam.PolicyStatement(
                actions=["batch:UpdateComputeEnvironment"],
                resources=[batch_compute_env_arn]),
                iam.PolicyStatement(
                actions=["batch:UpdateJobQueue"],
                resources=[batch_job_queue_arn])]
            ))
        
        # Stop New Jobs Lambda Function
        stop_new_jobs_lambda_function = lambda_.Function(
            self, 'stop-new-jobs-lambda-function',
            code=lambda_.Code.from_asset('./serverless_batch_cost_guardian/lambdas'),
            handler='stop_new_batch_job_submissions.lambda_handler',
            role=stop_new_jobs_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'BATCH_COMPUTE_ENV_NAME': batch_compute_env_name.value_as_string, 
                'BATCH_JOB_QUEUE_NAME': batch_job_queue_name.value_as_string 
            }
        )
        
        ###
        
        # DynamoDB Batch ECS Running Task Table
        batch_ecs_running_tasks_table = dynamodb.Table(self, "batch-ecs-running-tasks-table",
            partition_key=dynamodb.Attribute(name="taskArn", type=dynamodb.AttributeType.STRING),
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
        )
                
        # DynamoDB Batch ECS Aggregate Table
        batch_ecs_aggregate_table = dynamodb.Table(self, "batch-ecs-aggregate-table",
            partition_key=dynamodb.Attribute(name="aggregate_key", type=dynamodb.AttributeType.STRING)
        )
        
        # Write Tasks to Dynamo Lambda IAM Role
        write_tasks_to_dynamo_lambda_role = iam.Role(scope=self, id='write-tasks-to-dynamo-lambda-iam-role',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name='write-tasks-to-dynamo-lambda-iam-role',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole') 
            ])
        
        # Input parameter Batch Compute Env Underlying ECS Cluster: 
        ecs_cluster_arn = core.CfnParameter(self, 'ecsClusterArn',
          type='String',
          description='ARN of Batch Compute Environment ECS Cluster'
        ) 
        
        # Scoped down customer managed policy to allow Lambda access to Batch, DynamoDB, and ECS
        write_tasks_to_dynamo_lambda_role.attach_inline_policy(iam.Policy(self, "batch-dynamo-ecs-policy",
            statements=[iam.PolicyStatement(
                actions=["batch:DescribeComputeEnvironments"],
                resources=["*"]),
                iam.PolicyStatement(
                actions=[
                  "ecs:ListTasks",
                  "ecs:DescribeTasks"
                ],
                resources=["*"], # resource type might need to be task and/or container instance but let's see if cluster is enough
                conditions={"ArnEquals": { # maybe StringEquals
                    "ecs:cluster": ecs_cluster_arn.value_as_string}}),  
                iam.PolicyStatement(
                actions=["dynamodb:PutItem"],
                resources=[
                    batch_ecs_running_tasks_table.table_arn,
                    batch_ecs_aggregate_table.table_arn 
                ])] 
            ))
            
        write_tasks_to_dynamo_lambda_role.node.add_dependency(batch_ecs_running_tasks_table)
        write_tasks_to_dynamo_lambda_role.node.add_dependency(batch_ecs_aggregate_table)
        
        # Write Tasks to Dynamo Lambda Function
        write_tasks_to_dynamo_lambda_function = lambda_.Function(
            self, 'write-tasks-to-dynamo-lambda-function',
            code=lambda_.Code.from_asset('./serverless_batch_cost_guardian/lambdas'),
            handler='write_batch_ecs_tasks_to_dynamo.lambda_handler',
            role=write_tasks_to_dynamo_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'BATCH_COMPUTE_ENV_NAME': batch_compute_env_name.value_as_string, 
                'RUNNING_TABLE_NAME': batch_ecs_running_tasks_table.table_name,
                'AGGREGATE_TABLE_NAME': batch_ecs_aggregate_table.table_name 
            }
        )
        
        write_tasks_to_dynamo_lambda_function.node.add_dependency(write_tasks_to_dynamo_lambda_role)
        
        ###
        
        # Update Aggregate ECS Task Table Lambda IAM Role
        update_aggregate_ecs_task_table_lambda_role = iam.Role(scope=self, id='update-aggregate-ecs-task-table-lambda-iam-role',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name='update-aggregate-ecs-task-table-lambda-iam-role',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole') 
            ])
        
        # Scoped down customer managed policy to allow Lambda access to DynamoDB
        update_aggregate_ecs_task_table_lambda_role.attach_inline_policy(iam.Policy(self, "dynamo-update-policy",
            statements=[iam.PolicyStatement(
                actions=["dynamodb:UpdateItem"],
                resources=[
                    batch_ecs_aggregate_table.table_arn 
                ])] 
            ))
            
        update_aggregate_ecs_task_table_lambda_role.node.add_dependency(batch_ecs_aggregate_table)
        
        # Update Aggregate ECS Task Table Lambda Function
        update_aggregate_ecs_task_table_lambda_function = lambda_.Function(
            self, 'update-aggregate-ecs-task-table-lambda-function',
            code=lambda_.Code.from_asset('./serverless_batch_cost_guardian/lambdas'),
            handler='update_aggregate_ecs_task_table.lambda_handler',
            role=update_aggregate_ecs_task_table_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'AGGREGATE_TABLE_NAME': batch_ecs_aggregate_table.table_name 
            }
        )
        
        update_aggregate_ecs_task_table_lambda_function.add_event_source(lambda_events.DynamoEventSource(batch_ecs_running_tasks_table,
            starting_position=lambda_.StartingPosition.LATEST,
            batch_size=100,
            bisect_batch_on_error=False
        ))
        
        update_aggregate_ecs_task_table_lambda_function.node.add_dependency(update_aggregate_ecs_task_table_lambda_role)
        
        ###
        
        # Delete ECS Task From Dynamo Lambda IAM Role
        delete_ecs_task_from_dynamo_lambda_role = iam.Role(scope=self, id='delete-ecs-task-from-dynamo-lambda-iam-role',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name='delete-ecs-task-from-dynamo-lambda-iam-role',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole') 
            ])
        
        # Scoped down customer managed policy to allow Lambda access to DynamoDB
        delete_ecs_task_from_dynamo_lambda_role.attach_inline_policy(iam.Policy(self, "dynamo-delete-policy",
            statements=[iam.PolicyStatement(
                actions=["dynamodb:DeleteItem"],
                resources=[
                    batch_ecs_running_tasks_table.table_arn 
                ])] 
            ))
        
        delete_ecs_task_from_dynamo_lambda_role.node.add_dependency(batch_ecs_running_tasks_table)
        
        # Delete ECS Task From Dynamo Lambda Function
        delete_ecs_task_from_dynamo_lambda_function = lambda_.Function(
            self, 'delete-ecs-task-from-dynamo-lambda-function',
            code=lambda_.Code.from_asset('./serverless_batch_cost_guardian/lambdas'),
            handler='delete_ecs_task_from_dynamo.lambda_handler',
            role=delete_ecs_task_from_dynamo_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'RUNNING_TABLE_NAME': batch_ecs_running_tasks_table.table_name 
            }
        )
        
        delete_ecs_task_from_dynamo_lambda_function.node.add_dependency(delete_ecs_task_from_dynamo_lambda_role)
        
        # EventBridge Trigger for Delete ECS Task From Dynamo Lambda Function
        eventbridge_catch_deleted_ecs_tasks_rule = aws_events.Rule(self, "eventbridge-catch-deleted-ecs-tasks-rule",
            event_pattern=aws_events.EventPattern(
                detail_type=["ECS Task State Change"],
                source=["aws.ecs"],
                detail={
                    "clusterArn": [ecs_cluster_arn.value_as_string],
                    "lastStatus": ["STOPPED"]
                }
            )
        )
        
        eventbridge_catch_deleted_ecs_tasks_rule.add_target(aws_targets.LambdaFunction(delete_ecs_task_from_dynamo_lambda_function))

        ###
        
        # DynamoDB Latest Timestamp and Running Cost Table
        latest_timestamp_running_cost_table = dynamodb.Table(self, "latest-timestamp-running-cost-table",
            partition_key=dynamodb.Attribute(name="partition-key", type=dynamodb.AttributeType.STRING)
        )
        
        # High Velocity Batch Spend Checker Lambda IAM Role
        high_velocity_batch_spend_checker_lambda_role = iam.Role(scope=self, id='high-velocity-batch-spend-checker-lambda-iam-role',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name='high-velocity-batch-spend-checker-lambda-iam-role',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole') 
            ])

        # Scoped down customer managed policy to allow Lambda access to DynamoDB
        high_velocity_batch_spend_checker_lambda_role.attach_inline_policy(iam.Policy(self, "dynamo-get-update-policy",
            statements=[iam.PolicyStatement(
                actions=[
                  "dynamodb:UpdateItem",
                  "dynamodb:GetItem"
                ],
                resources=[
                    batch_ecs_aggregate_table.table_arn,
                    latest_timestamp_running_cost_table.table_arn
                ])] 
            ))
        
        high_velocity_batch_spend_checker_lambda_role.node.add_dependency(batch_ecs_aggregate_table)
        high_velocity_batch_spend_checker_lambda_role.node.add_dependency(latest_timestamp_running_cost_table)
        
        # High Velocity Batch Spend Checker Lambda Function
        high_velocity_batch_spend_checker_lambda_function = lambda_.Function(
            self, 'high-velocity-batch-spend-checker-lambda-function',
            code=lambda_.Code.from_asset('./serverless_batch_cost_guardian/lambdas'),
            handler='high_velocity_batch_spend_checker.lambda_handler',
            role=high_velocity_batch_spend_checker_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'AGGREGATE_TABLE_NAME': batch_ecs_aggregate_table.table_name,
                'LATEST_TIMESTAMP_RUNNING_COST_TABLE_NAME': latest_timestamp_running_cost_table.table_name
            }
        )
        
        high_velocity_batch_spend_checker_lambda_function.node.add_dependency(high_velocity_batch_spend_checker_lambda_role)
        
        ###
        
        # Stop Running Batch Jobs Lambda IAM Role
        stop_running_batch_jobs_lambda_role = iam.Role(scope=self, id='stop-running-batch-jobs-lambda-iam-role',
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name='stop-running-batch-jobs-lambda-iam-role',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole') 
            ])
        
        # Scoped down customer managed policy to allow Lambda access to Batch
        stop_running_batch_jobs_lambda_role.attach_inline_policy(iam.Policy(self, "batch-list-terminate-policy",
            statements=[iam.PolicyStatement(
                actions=[
                  "batch:ListJobs",
                  "batch:TerminateJob"
                ],
                resources=[
                    "*"
                ])] 
            ))
            
        # Stop Running Batch Jobs Lambda Function
        stop_running_batch_jobs_lambda_function = lambda_.Function(
            self, 'stop-running-batch-jobs-lambda-function',
            code=lambda_.Code.from_asset('./serverless_batch_cost_guardian/lambdas'),
            handler='stop_running_batch_jobs.lambda_handler',
            role=stop_running_batch_jobs_lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'BATCH_JOB_QUEUE_NAME': batch_job_queue_name.value_as_string
            }
        )
        
        stop_running_batch_jobs_lambda_function.node.add_dependency(stop_running_batch_jobs_lambda_role)
        
        ###
        
        # Step Functions State Machine IAM Role
        step_functions_state_machine_iam_role = iam.Role(scope=self, id='step-functions-state-machine-iam-role',
            assumed_by = iam.ServicePrincipal('states.amazonaws.com'),
            role_name='step-functions-state-machine-iam-role'
            )
            
        # Scoped down customer managed policy to allow Step Functions access to Lambda and DynamoDB
        step_functions_state_machine_iam_role.attach_inline_policy(iam.Policy(self, "lambda-invoke-dynamodb-put-policy",
            statements=[iam.PolicyStatement(
                actions=[
                  "dynamodb:PutItem"
                ],
                resources=[
                    latest_timestamp_running_cost_table.table_arn
                ]),
                iam.PolicyStatement(
                actions=[
                    "lambda:Invoke"
                ],
                resources=[
                    stop_new_jobs_lambda_function.function_arn,
                    write_tasks_to_dynamo_lambda_function.function_arn,
                    high_velocity_batch_spend_checker_lambda_function.function_arn,
                    stop_running_batch_jobs_lambda_function.function_arn
                ])] 
            ))
        
        step_functions_state_machine_iam_role.node.add_dependency(latest_timestamp_running_cost_table)
        step_functions_state_machine_iam_role.node.add_dependency(stop_new_jobs_lambda_function)
        step_functions_state_machine_iam_role.node.add_dependency(write_tasks_to_dynamo_lambda_function)
        step_functions_state_machine_iam_role.node.add_dependency(high_velocity_batch_spend_checker_lambda_function)
        step_functions_state_machine_iam_role.node.add_dependency(stop_running_batch_jobs_lambda_function)
        
        stop_new_batch_job_submissions = tasks.LambdaInvoke(self, "stop-new-batch-job-submissions",
            lambda_function=stop_new_jobs_lambda_function,
            output_path="$.Payload"
        )
        
        write_batch_ecs_tasks_to_dynamo = tasks.LambdaInvoke(self, "write-batch-ecs-tasks-to-dynamo",
            lambda_function=write_tasks_to_dynamo_lambda_function,
            output_path="$.Payload"
        )
  
        initialize_start_time_and_cost = tasks.DynamoPutItem(self, "initialize-start-time-and-cost",
            item={
                "partition-key": tasks.DynamoAttributeValue.from_string("pk"),
                "latestTimeStamp": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.startTime")),
                "runningCost": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.startCost"))
            },
            table=latest_timestamp_running_cost_table,
            result_path=sfn.JsonPath.DISCARD
        )
        
        budget_met_choice_state = sfn.Choice(self, "budget_met_choice_state")
        
        high_velocity_batch_spend_checker = tasks.LambdaInvoke(self, "high-velocity-batch-spend-checker",
            lambda_function=high_velocity_batch_spend_checker_lambda_function,
            output_path="$.Payload"
        )
        
        # Input parameter configurable polling rate for high frequcency Batch spend checker 
        wait_time_parameter = core.CfnParameter(self, 'waitTime',
          type='Number',
          description='Configurable polling rate (in seconds) for high frequcency Batch spend checker'
        )
        
        wait_time = sfn.Wait(self, "Wait",
            time=sfn.WaitTime.duration(
                core.Duration.seconds(wait_time_parameter.value_as_number))
        )
 
        stop_running_batch_jobs = tasks.LambdaInvoke(self, "stop-running-batch-jobs",
            lambda_function=stop_running_batch_jobs_lambda_function,
            output_path="$.Payload"
        )
        
        definition = stop_new_batch_job_submissions \
            .next(write_batch_ecs_tasks_to_dynamo) \
            .next(initialize_start_time_and_cost) \
            .next(budget_met_choice_state \
             .when(sfn.Condition.string_matches("$.budgetMet", "YES"), stop_running_batch_jobs) \
             .when(sfn.Condition.string_matches("$.budgetMet", "NO"), high_velocity_batch_spend_checker.next(wait_time).next(budget_met_choice_state)))
            
        serverless_batch_cost_guardian_state_machine = sfn.StateMachine(self, "serverless-batch-cost-guardian-state-machine",
            definition=definition,
            role=step_functions_state_machine_iam_role
        )
        
        serverless_batch_cost_guardian_state_machine.node.add_dependency(step_functions_state_machine_iam_role)
        
        
        
        