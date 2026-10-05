# Serving Recommendation Lambda API

This directory contains the code and configuration for the serving AI recommendation Lambda function.

## Components

* **`bgg_recommender.py`**: The Lambda handler entry point. It:
  1. Receives a BGG username query parameter (and optional filters like publishing year range).
  2. Checks if the user's collection Parquet file exists in S3 (`s3://boardgame-app/data/users/{username}.parquet`). If not, it dispatches a scraping message to the SQS queue and returns a `{"status": "scraping"}` response.
  3. Downloads and parses the combined boardgame catalog Parquet files from S3.
  4. Filters candidates based on user rated games (excluding already owned/rated games unless requested otherwise).
  5. Computes a similarity score using **Jaccard Similarity** matching between user rated game categories/mechanics and candidate game categories/mechanics.
  6. Prompts Amazon Bedrock (**Amazon Nova Micro**) to rank the candidates, select the top 10, and write personalized AI reasoning explanations.
* **`combine_raw_to_single_file.py`**: The entry point for the `bgg_compactor` Lambda function. It downloads thousands of raw, single-game Parquet files from S3, aligns their schemas, merges them into a single pandas/PyArrow table, Snappy-compresses them, and uploads the final `catalog.parquet` table back to S3.
* **`Dockerfile`**: Configures the container base layer to build the function run inside the AWS Lambda environment (shared by both the recommender and compactor entry points).
* **`requirements.txt`**: List of dependencies (`pandas`, `numpy`, `pyarrow`, `boto3`).

## Configuration (Environment Variables)

The function uses the following variables (injected via Terraform):
* `S3_OUTPUT_BUCKET_NAME`: The S3 data lake bucket name (default: `boardgame-app`).
* `USER_SQS_QUEUE_URL`: SQS queue URL used to trigger the user profile scraper asynchronously.
* `BEDROCK_MODEL_ID`: Bedrock LLM ID used for generating recommendations (default: `amazon.nova-micro-v1:0`).

## Taste Profile Schema (`data/users/{username}_taste_profile.json`)

User taste profiles are generated asynchronously by `bgg_taste_analytics` upon collection scrape, or computed inline by `scoring.py`. The profile applies logarithmic damping and catalog-wide Inverse Document Frequency (IDF) discounting to elevate distinctive preferences over ubiquitous tags:

```json
{
  "mech_weights": {
    "Trick-taking": 14.52,
    "Hand Management": 6.84
  },
  "cat_weights": {
    "Economic": 8.75,
    "Card Game": 4.12
  },
  "raw_mech_weights": {
    "Trick-taking": 3.76,
    "Hand Management": 4.88
  },
  "raw_cat_weights": {
    "Economic": 3.42,
    "Card Game": 4.15
  },
  "complexity_weights": {
    "Light": 0.0,
    "Medium-Light": 2.5,
    "Medium-Heavy": 4.0,
    "Heavy": 1.0
  },
  "user_mean_complexity": 2.85,
  "designer_weights": {
    "Uwe Rosenberg": 4.2
  },
  "publisher_weights": {
    "Lookout Games": 4.2
  },
  "idf_applied": true,
  "generated_at": "2026-10-05T13:20:00.000000+00:00"
}
```

* `mech_weights` / `cat_weights`: Final TF-IDF weighted affinity scores used in cosine similarity candidate scoring.
* `raw_mech_weights` / `raw_cat_weights`: Raw logarithmically damped affinities before IDF scaling.
* `user_mean_complexity`: Rating-weighted average complexity (1.0–5.0) of user's liked games.
* `idf_applied`: Boolean indicator indicating TF-IDF catalog frequency discounting is applied.

