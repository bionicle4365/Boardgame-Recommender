# BGG User Data Scraper Lambda

This directory contains the SQS-triggered Python container code running inside AWS Lambda that downloads a user's board game collection from BoardGameGeek.

## Components

* **`bgg_user_data_scraper.py`**:
  1. Triggered by SQS messages containing BGG usernames.
  2. Queries the BGG API `collection` endpoint (retrying up to 3 times to handle slow responses or 202 accepted states).
  3. Parses the XML response to extract each game ID, rating (if rated), and ownership status.
  4. Saves the collection as a consolidated Parquet file directly to S3 (`s3://boardgame-app/data/users/{username}.parquet`).
* **`Dockerfile`**: Packages the script for AWS Lambda deployment.
* **`requirements.txt`**: Standard dependencies (`pandas`, `pyarrow`, `boto3`, `requests`).

## Configuration (Environment Variables)

* `S3_OUTPUT_BUCKET_NAME`: Target S3 bucket name (default: `boardgame-app`).
* `BGG_API_TOKEN`: Optional authorization token to query BGG.
