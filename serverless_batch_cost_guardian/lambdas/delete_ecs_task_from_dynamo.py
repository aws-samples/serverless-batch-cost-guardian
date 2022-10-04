import json
import boto3
import os 

dynamodb_resource = boto3.resource('dynamodb')
table_name =  os.environ['RUNNING_TABLE_NAME']

def lambda_handler(event, context):
    
    taskArn = event['detail']['taskArn']
    
    table = dynamodb_resource.Table(table_name)
    
    response = table.delete_item(Key = {'taskArn': taskArn})

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
