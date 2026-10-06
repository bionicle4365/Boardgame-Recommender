# Terraform Infrastructure Modules

This directory contains the HashiCorp Terraform configuration modules to build and deploy the serverless AWS backend architecture.

---

## Layout & Modules

* **`main.tf`**: The root module coordinating variable interpolation across submodules.
* **`variables.tf`**: Root inputs (such as AWS region, project naming, and container tags).
* **`config.s3.tfbackend`**: S3 remote backend configuration to securely store Terraform state.
* **`s3/`**: Sets up S3 buckets for raw data, processed user profiles, cafe inventories (`data/cafes/`), convention data, and recommendation caches.
* **`sqs/`**: Deploys the decoupled SQS message queues (`bgg_game_data_scraper_queue` and `bgg_user_data_scraper_queue`) with dead-letter queue (DLQ) support.
* **`iam/`**: Provisions IAM roles and least-privilege policies for ECS Fargate, Lambdas, Bedrock Converse API invocation, and SSM parameter access.
* **`lambda/`**: Provisions API serving Lambdas (containerized Recommender) and Python runtime Lambdas (Preferences, Scrapers, Proxy, Analytics, Compactor).
* **`ecs/`**: Configures ECS task definitions and execution tasks for the continuous Fargate container scraper.
* **`apigateway/`**: Provisions the API Gateway HTTP REST API, CORS policies, gzip response compression, Cognito authorizer, and routes (`/recommendations`, `/profile`, `/session`, `/sessions`, `/cafe/vote/start`, `/preferences`, `/collection`, `/cafe/*`).
* **`cognito/`**: Configures the Amazon Cognito User Pool and Client for user registration, login, JWT token issuance, and SES email verification.
* **`dynamodb/`**: Provisions DynamoDB tables:
  - `bgg-user-preferences`: Stores user custom scoring weights, playgroups, and settings.
  - `bgg-game-night-sessions`: Ephemeral voting sessions with TTL and creator GSI.
  - `bgg-cafes`: Venue registry with vanity slug PK and `owner_cognito_id-index` GSI.
* **`eventbridge/`**: Configures automated cron schedules for monthly recent game scans and weekly cafe collection syncs.
