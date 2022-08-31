import json
import boto3
import os

def lambda_handler(event, context):
    
    # 1: Update compute environment with state disabled 
    # https://docs.aws.amazon.com/batch/latest/APIReference/API_UpdateComputeEnvironment.html
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/batch.html#Batch.Client.update_compute_environment
    
    # 2: Update job queue with state disabled 
    
    batch_client = boto3.client('batch')
    
    # 1
    response = batch_client.update_compute_environment(
        computeEnvironment=os.environ['BATCH_COMPUTE_ENV_NAME'], 
        state='DISABLED'
    )
    
    # 2
    response = batch_client.update_job_queue(
        jobQueue=os.environ['BATCH_JOB_QUEUE_NAME'],
        state='DISABLED'
    )
    
    return {
        'statusCode': 200,
        "startTime": event['startTime'],
        "startCost": event['startCost'],
        "budgetLimit": event['budgetLimit']
    }
