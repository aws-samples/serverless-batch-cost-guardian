import json
import boto3
import os

def lambda_handler(event, context):
    # Terminate all jobs (applies to all runnable, starting, pending, starting, and running jobs)
    # https://aws.amazon.com/premiumsupport/knowledge-center/batch-jobs-termination/ 
    # https://www.tutorialspoint.com/how-to-use-boto3-to-get-the-details-of-multiple-glue-jobs-at-a-time
    # https://dev.classmethod.jp/articles/count-aws-batch-queue-by-custom-metrics/
   
    batch_client = boto3.client('batch')

    statuses = ['SUBMITTED','PENDING','RUNNABLE','STARTING','RUNNING']
    
    for status in statuses:
        response = batch_client.list_jobs(
            jobQueue=os.environ['BATCH_JOB_QUEUE_NAME'],
            jobStatus=status 
        ) 
        for x in response['jobSummaryList']: 
            print(x['jobId'])
            response = batch_client.terminate_job(
                jobId=x['jobId'],
                reason='nuke-jobs-budget-met'
            )

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
