# Terraform Infrastructure Modules

This directory contains the Terraform configuration files to build and deploy the serverless AWS backend architecture.

## Layout & Modules

* **`main.tf`**: The root module coordinating variable interpolation across submodules.
* **`variables.tf`**: Root inputs (such as AWS region).
* **`config.s3.tfbackend`**: S3 backend configuration file to store state in a remote bucket.
* **`s3/`**: Sets up S3 buckets for raw data, processed user profiles, scripts, and temp directories.
* **`sqs/`**: Deploys the SQS message queues (`bgg_game_data_scraper_queue` and `bgg_user_data_scraper_queue`) for decoupled task processing.
* **`iam/`**: Provisions IAM roles and custom policies for Glue, ECS, Lambda, Bedrock invocation, and SSM parameters access.
* **`lambda/`**: Provisions API serving Lambdas and SQS-triggered scraper Lambdas, referencing ECR container registry images.
* **`ecs/`**: Configures ECS task definitions and execution tasks for the continuous Fargate container scraper.
* **`apigateway.tf`**: Provisions the API Gateway HTTP APIs and routes mapping `/recommendations`, secure `/preferences` endpoints, and `/collection` API proxy.
* **`cognito.tf`**: Configures the Amazon Cognito User Pool and Client for user registration, login, and JWT-based token generation.
* **`dynamodb.tf`**: Configures the DynamoDB database table `bgg-user-preferences` to persist user-specific weights, playgroups, and settings.
* **`glue/`**: *(Deprecated)* Glue catalog database and schemas. Commented out in `main.tf` in favor of the serverless compactor Lambda.

