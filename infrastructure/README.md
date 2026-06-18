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
* **`apigateway.tf`**: Provisions the API Gateway REST APIs and HTTP routes mapping `/recommendations` to the serving Lambda.
* **`glue/`**: Deploys the Glue Catalog Database, raw crawlers, and scheduled ETL Spark workflow compaction jobs (`boardgame-data-workflow`).
