---
name: aws-architecture-expert
description: Specializes in modifying, reviewing, and provisioning infrastructure across AWS (Lambda, ECS, DynamoDB, Cognito, S3, SQS, API Gateway, EventBridge) using Terraform. Use this skill when modifying Terraform configurations, AWS services, IAM policies, or serverless topologies.
---

## Guidelines for AWS & Terraform Operations

### Deployment Rules
- **DO NOT execute `terraform apply` directly.** Let the user execute it or rely on CI/CD pipelines. You may run `terraform plan` or `terraform validate` to check configurations.
- **IAM Principle of Least Privilege**: When updating Terraform modules or adding IAM role policies, always restrict resources to the minimum necessary actions.

### Resource Guidelines
- **Lambda Functions**: Check RAM, timeout settings, and environment variables. Note that LightFM was deprecated; recommender uses heuristic scoring with Bedrock Nova Lite (`amazon.nova-lite-v1:0`) and S3 Parquet datasets.
  - Active Lambdas in [infrastructure/lambda/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/lambda/main.tf):
    - `bgg_game_data_scraper`: Image-based bulk game scraper (SQS-triggered, 100 games/batch).
    - `bgg_user_data_scraper`: Image-based user and cafe collection scraper (`is_cafe=true` support).
    - `bgg_api_proxy`: Python 3.12 zip Lambda serving as a CORS reverse proxy for the BGG XML API2.
    - `bgg_recommender`: Image-based recommender engine with Bedrock Nova Lite integration and session management.
    - `bgg_compactor`: Image-based PyArrow/Pandas S3 compaction pipeline replacing Glue/Athena.
    - `bgg_preferences`: Python 3.12 zip Lambda with Pandas layer managing user preferences and cafe venue registry.
    - `bgg_taste_analytics`: Image-based taste profile aggregator.
    - `bgg_preview_refresh`: Python 3.12 zip Lambda refreshing upcoming convention preview datasets in S3.
- **DynamoDB**: Managed via [infrastructure/dynamodb/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/dynamodb/main.tf):
  - `bgg-user-preferences` (PK: `userId` [S])
  - `bgg-cafes` (PK: `cafe_id` [S], GSI: `owner_cognito_id-index`)
  - `bgg-game-night-sessions` (PK: `session_id` [S], GSI: `creator_id-created_at-index`, TTL: `expires_at`)
- **EventBridge**: Scheduled rules in [infrastructure/eventbridge/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/eventbridge/main.tf) trigger periodic preview refreshes and weekly cafe syncs.
- **SQS**: Use SQS for decoupling scrapers and analytics queues, with Dead Letter Queues (DLQs) and concurrency limits defined in [infrastructure/sqs/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/sqs/main.tf).
- **Cognito**: Handle secure user pool attributes and authorizers on API Gateway endpoints.

### Cost Control & Budgeting Guidelines
- **Serverless Bias**: Favor serverless pricing models (Lambda, SQS, API Gateway, DynamoDB On-Demand) to keep idle environment costs to zero.
- **Ingress Throttling**: API Gateway traffic rate limits are defined at [infrastructure/apigateway/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/apigateway/main.tf) (`throttling_rate_limit = 5`, `throttling_burst_limit = 10`) to prevent billing spikes from DDoS or rapid client calls.
- **Resource Constraints**: Limit Lambda execution costs by setting low timeout values and configuring `reserved_concurrent_executions` based on `data_lambda_concurrency_limit` and `user_lambda_concurrency_limit`.
- **Bypass Expensive AWS Services**: Keep costly services disabled or bypassed (e.g., bypass Glue crawlers and Athena queries; process compaction in-memory using Lambda and PyArrow via `bgg_compactor`).
- **Messaging Flow Rate**: Use SQS batching and concurrency controls defined in [infrastructure/sqs/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/sqs/main.tf) to smooth ingestion spikes.

### Key Files
- All directories under [infrastructure/](file:///d:/Git/Boardgame-Recommender/infrastructure/):
  - [infrastructure/lambda/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/lambda/main.tf)
  - [infrastructure/dynamodb/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/dynamodb/main.tf)
  - [infrastructure/apigateway/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/apigateway/main.tf)
  - [infrastructure/eventbridge/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/eventbridge/main.tf)
  - [infrastructure/s3/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/s3/main.tf)
  - [infrastructure/sqs/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/sqs/main.tf)
  - [infrastructure/ecr/](file:///d:/Git/Boardgame-Recommender/infrastructure/ecr/)
