import sys
import os

# Set mock env variables globally for all tests to satisfy boto3 / env setups
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'TESTING_DO_NOT_USE'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'TESTING_DO_NOT_USE'
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'test-bucket'
os.environ['USER_SQS_QUEUE_URL'] = 'https://sqs.test.com'
os.environ['BGG_API_TOKEN'] = 'test-token'
os.environ['BGG_TESTING'] = 'true'

# Mock aws_lambda_powertools inject_lambda_context to avoid AttributeError when context is None in tests
try:
    import aws_lambda_powertools
    aws_lambda_powertools.Logger.inject_lambda_context = lambda self, func: func
except ImportError:
    pass
