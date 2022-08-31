#!/usr/bin/env python3
import os
import aws_cdk as cdk

from serverless_batch_cost_guardian.infrastructure import ServerlessBatchCostGuardianStack, GUARDIAN_STACK_PREFIX
from sample_batch_env.infrastructure import AwsCdkFargateBatchStack, STACK_PREFIX
from event_driven_budget_checker.infrastructure import AwsCdkBudgetCheckerStack, BUDGET_STACK_PREFIX

app = cdk.App()
AwsCdkFargateBatchStack(app, f"{STACK_PREFIX}-batch-stack")
AwsCdkBudgetCheckerStack(app, f"{BUDGET_STACK_PREFIX}-budget-stack")
ServerlessBatchCostGuardianStack(app, f"{GUARDIAN_STACK_PREFIX}-guardian-stack")

app.synth()
