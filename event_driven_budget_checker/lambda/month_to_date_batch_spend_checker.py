import json
import boto3
import os
from dateutil import relativedelta
import datetime

# Create a Cost Explorer client
ce_client = boto3.client('ce')

# Create a Budgets client
budgets_client = boto3.client('budgets')

def lambda_handler(event, context):

    # NEW date range calculation 
    
    todayDate = datetime.date.today()
    
    # get beginning of month before incrementing 
    # (not doing this would cause errors on last day of the month)
    beginningMonthDate = todayDate.replace(day=1) 
    
    # account for end date in cost API being exclusive
    # (aka the end date is not counted so we add one)
    todayDate += datetime.timedelta(1) 
            
    formattedBeginningMonthDate = beginningMonthDate.strftime('%Y-%m-%d')
    formattedTodayDate = todayDate.strftime('%Y-%m-%d')
    
    response = ce_client.get_cost_and_usage(
            TimePeriod={"Start": formattedBeginningMonthDate, "End": formattedTodayDate},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={
            	"And": [{
            			'Dimensions': {
            				'Key': 'SERVICE',
            				'Values': [
            					'Amazon Elastic Container Service',
            				],
            				'MatchOptions': [
            					'EQUALS',
            				]
            			}
            		},
            		{
            			'Tags': {
            				'Key': 'aws:batch:compute-environment',
            				'Values': [
            					os.environ['BATCH_COMPUTE_ENV_NAME'],
            				],
            				'MatchOptions': [
            					'EQUALS',
            				]
            			}
            		}
            	]
            }
    )
    
    amount = response["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
    output = "%.3f" % float(amount)
    
    ###
    
    account = os.environ['ACCOUNT_ID']
    budget = os.environ['BUDGET_NAME']
    
    response = budgets_client.describe_budget(
            AccountId=account,
            BudgetName=budget
    )
    
    budget_limit = response['Budget']['BudgetLimit']['Amount']
    
    msg = "Cost Explorer says you spent $" + output + " (USD) out of Budget limit $" + budget_limit + " (USD)."
    client = boto3.client('sns')
    arn = os.environ['SNS_ARN']
    subject = "AWS Current Batch Spend this Month."

    response = client.publish(
    		TopicArn=arn,
    		Message=msg,
    		Subject=subject,
    )
    
    ###
    
    # Check if threshold reached 
    
    percent_used = percent(output, budget_limit)
    
    if percent_used >= int(os.environ['DESIRED_BUDGET_THRESHOLD_PERCENT']):
        
        print("Budget threshold reached. Invoking Cost Guardian now.")
        
        if os.environ['COST_GUARDIAN_STATE_MACHINE_ARN'] == '':
            return {"statusCode": 200, "body": "Please set Cost Guardian ARN as an input parameter."}
            
        # actually kick in step functions poller
        # pass timestamp in as input so Lambda poller can compare time diff on each 
        
        client = boto3.client('stepfunctions')
        response = client.start_execution(
            stateMachineArn=os.environ['COST_GUARDIAN_STATE_MACHINE_ARN'],  
            input=json.dumps({ 
                'startTime': str(datetime.datetime.now()), 
                'startCost': output,
                'budgetLimit': budget_limit
            })
        )

    return {"statusCode": 200, "body": msg}

def percent(part, whole):
    return 100 * float(part)/float(whole)
