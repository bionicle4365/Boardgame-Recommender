from pyathena import connect
import pandas as pd
from bgg_user_data_scraper import lambda_handler
conn = connect(s3_staging_dir="s3://boardgame-data/test-items/athena-results/",
                   region_name="us-east-1")

query = "SELECT DISTINCT user_id FROM boardgame_app.bg_users"

df = pd.read_sql(query, conn)

username_list = df['user_id'].tolist()
event_list = []
for username in username_list:
    event = {
                "messageId": "msg1",
                "body": username,
                "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""
            }
    event_list.append(event)

records = { "Records": event_list }
lambda_handler(records, None)
