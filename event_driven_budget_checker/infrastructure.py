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
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3_notify
from aws_cdk import aws_kms as kms

# input parameters = Batch compute env name/ARN, CUR S3 bucket name/ARN, 
# desired threshold % before high frequency checker kicks in, email for SNS 
# budget notification updates, cost guardian Step Functions ARN

BUDGET_STACK_PREFIX = "event-driven-budget-checker"

SNS_TOPIC_NAME = BUDGET_STACK_PREFIX + "-sns-topic"
SNS_TOPIC_DISPLAY_NAME = "SNS Budget Alert Topic"

LAMBDA_IAM_ROLE_ID = BUDGET_STACK_PREFIX + "-lambda-iam-role-id"
LAMBDA_IAM_ROLE_NAME = BUDGET_STACK_PREFIX + "-lambda-iam-role-name"

LAMBDA_FUNCTION_NAME = "month_to_date_batch_spend_checker"

IMPORTED_S3_BUCKET = "S3-CUR-Bucket"

class AwsCdkBudgetCheckerStack(core.Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        # KMS CMK for SNS Topic SSE at rest
        kms_key = kms.Key(self, "SnsKmsKey",
            enable_key_rotation=True,
            pending_window=core.Duration.days(7),
            removal_policy=core.RemovalPolicy.DESTROY,
            alias="alias/sns_kms_key",
            description='KMS key for encrypting SNS topic messages at rest',
        )
       
        # SNS Topic and Subscription
        sns_email = core.CfnParameter(self, 'snsEmail',
          type='String',
          description='email for SNS budget notification updates'
        )
        
        sns_topic = sns.Topic(self, SNS_TOPIC_NAME, 
          display_name=SNS_TOPIC_DISPLAY_NAME,
          master_key=kms_key
        )
        
        topic_policy = sns.TopicPolicy(self, "TopicPolicy",
            topics=[sns_topic]
        )
        
        # Ensure encryption in transit 
        topic_policy.document.add_statements(iam.PolicyStatement(
            actions=["SNS:Publish"],
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()],
            resources=[sns_topic.topic_arn],
            conditions={"Bool": {
              "aws:SecureTransport": "false"}}
        ))

        sns_topic.add_subscription(subscriptions.EmailSubscription(sns_email.value_as_string))
        
        # IAM Role
        lambda_role = iam.Role(scope=self, id=LAMBDA_IAM_ROLE_ID,
            assumed_by = iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name=LAMBDA_IAM_ROLE_NAME,
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
            ])
        
        # Input Parameters as Lambda Environment Variables and Policy Resources
        
        account_id = core.CfnParameter(self, 'accountId',
          type='String',
          description='AWS Account ID number.'
        )
        
        budget_name = core.CfnParameter(self, 'budgetName',
          type='String',
          description='Name of the AWS Budget tracking your Batch compute environment tag.'
        )
        
        budget_arn = 'arn:aws:budgets::' + account_id.value_as_string + ':budget/' + budget_name.value_as_string
        
        # Add customer managed policy to allow Lambda access to Budgets, Cost Explorer, KMS, and SNS
        lambda_role.attach_inline_policy(iam.Policy(self, "budgets-cost-explorer-kms-sns-policy",
            statements=[iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[sns_topic.topic_arn]),
                iam.PolicyStatement(
                actions=[
                  "budgets:DescribeBudget",
                  "budgets:ViewBudget"
                ],
                resources=[budget_arn]),
                iam.PolicyStatement(
                actions=[
                  "kms:GenerateDataKey",
                  "kms:Decrypt"
                ],
                resources=[kms_key.key_arn]),
                iam.PolicyStatement(
                actions=["ce:GetCostAndUsage"],
                resources=["*"])]
            ))
        lambda_role.node.add_dependency(sns_topic)
          
        # Additional Input Parameters as Lambda Environment Variables
        batch_compute_env_name = core.CfnParameter(self, 'batchComputeEnvName',
          type='String',
          description='Name of your tagged AWS Batch compute environment.'
        )
        
        cost_guardian_state_machine_arn = core.CfnParameter(self, 'costGuardianStateMachineArn',
          type='String',
          description='ARN of the Cost Guardian Step Functions state machine. If you have not created this stack yet, please leave this parameter blank.'
        )
        
        # Add customer managed policy to allow Lambda access to Step Functions
        if cost_guardian_state_machine_arn.value_as_string: 
          lambda_role.attach_inline_policy(iam.Policy(self, "step-functions-policy",
            statements=[iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[cost_guardian_state_machine_arn.value_as_string])]
            ))
        
        desired_budget_threshold_percent = core.CfnParameter(self, 'desiredBudgetThresholdPercent',
          type='String',
          description='Desired Budget threshold to reach before invoking the serverless Cost Guardian.'
        )
        
        # Lambda Function
        lambda_function = lambda_.Function(
            self, LAMBDA_FUNCTION_NAME,
            code=lambda_.Code.from_asset('./event_driven_budget_checker/lambda'),
            handler='month_to_date_batch_spend_checker.lambda_handler',
            role=lambda_role,
            runtime=lambda_.Runtime.PYTHON_3_9,
            environment={
                'ACCOUNT_ID': account_id.value_as_string, 
                'BUDGET_NAME': budget_name.value_as_string, 
                'BATCH_COMPUTE_ENV_NAME': batch_compute_env_name.value_as_string, 
                'COST_GUARDIAN_STATE_MACHINE_ARN': cost_guardian_state_machine_arn.value_as_string, 
                'DESIRED_BUDGET_THRESHOLD_PERCENT': desired_budget_threshold_percent.value_as_string, 
                'SNS_ARN': sns_topic.topic_arn 
            }
        )
        lambda_function.node.add_dependency(sns_topic) 
        
        # Imported S3 CUR Bucket
        # NOTE: Must be deploying in same region as bucket 
        imported_s3_cur_bucket_name = core.CfnParameter(self, 's3CurBucketName',
          type='String',
          description='S3 Bucket for your Cost and Usage Reports'
        )
        
        s3_bucket = s3.Bucket.from_bucket_name(self, IMPORTED_S3_BUCKET, imported_s3_cur_bucket_name.value_as_string)
        
        # S3 Trigger
        s3_notification = s3_notify.LambdaDestination(lambda_function)
        s3_notification.bind(self, s3_bucket)
        
        s3_bucket.add_object_created_notification(s3_notification, s3.NotificationKeyFilter(suffix='.gz'))
