# Boardgame ID Continuous Scraper

This directory contains the Python container code running inside Amazon ECS (Fargate) that crawls the BoardGameGeek XMLAPI2 to discover active board game IDs.

## Components

* **`bgg_game_scraper.py`**: A continuous loop that:
  1. Pulls a starting game ID checkpoint from S3.
  2. Queries the BGG API `thing` endpoint for a batch of consecutive IDs (e.g., 20 at a time).
  3. Identifies elements where `type == 'boardgame'`.
  4. Pushes matching IDs to the SQS catalog scraper queue.
  5. Updates the S3 starting ID checkpoint dynamically.
* **`Dockerfile`**: Packages the script as a Docker image to run on AWS ECS Fargate.
* **`requirements.txt`**: Python dependencies (`requests`, `boto3`).

## Configuration (Environment Variables)

* `S3_BUCKET_NAME`: S3 bucket name storing checkpoints.
* `S3_KEY`: Key location of start ID checkpoint file (default: `bgg-scraper/bgg_start_id.txt`).
* `BATCH_SIZE`: Number of IDs to query per batch (Note: BGG limits this to `20`).
* `S3_UPDATE_INTERVAL`: S3 update checkpoint frequency (default: write starting ID to S3 every 100 IDs processed).
* `SQS_QUEUE_NAME`: Output SQS queue name (default: `bgg_game_data_scraper_queue`).
