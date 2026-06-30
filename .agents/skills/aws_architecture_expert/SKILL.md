---
name: AWS Architecture Expert
description: Specializes in modifying or deploying infrastructure across AWS (Lambda, ECS, DynamoDB, Cognito, S3, SQS, API Gateway) using Terraform.
---

## Guidelines for AWS & Terraform Operations

### Deployment Rules
- **DO NOT execute `terraform apply` directly.** Let the user execute it or rely on CI/CD pipelines. You may run `terraform plan` or `terraform validate` to check configurations.
- **IAM Principle of Least Privilege**: When updating Terraform modules or adding IAM role policies, always restrict resources to the minimum necessary actions.

### Resource Guidelines
- **Lambda Functions**: Check RAM, timeout settings, and environment variables. Be mindful of warmups and artifact downloading times (e.g., download of pickled LightFM model files from S3).
- **DynamoDB**: Verify Partition Keys and Sort Keys. Do not perform full table scans; query or scan using secondary indexes (GSIs) when appropriate.
- **SQS**: Use SQS for decoupling scrapers or analytics queues, ensuring retry limits/DLQs are configured.
- **Cognito**: Handle secure user pool attributes and SES mail integration correctly.

### Cost Control & Budgeting Guidelines
- **Serverless Bias**: Favor serverless pricing models (Lambda, SQS, API Gateway, DynamoDB On-Demand) to keep idle environment costs to zero.
- **Ingress Throttling**: API Gateway traffic rate limits are defined at [infrastructure/apigateway/main.tf:L18-21](file:///d:/Git/Boardgame-Recommender/infrastructure/apigateway/main.tf#L18-L21) (`throttling_rate_limit = 5`, `throttling_burst_limit = 10`) to prevent billing spikes from DDoS or rapid client calls.
- **Resource Constraints**: Limit Lambda execution costs by setting low timeout values and configuring `reserved_concurrent_executions` based on `data_lambda_concurrency_limit` and `user_lambda_concurrency_limit` as defined in [infrastructure/lambda/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/lambda/main.tf).
- **Bypass Expensive AWS Services**: Keep costly services disabled or bypassed (e.g., bypass Glue crawlers and Athena queries; process compaction in-memory using Lambda and PyArrow).
- **Messaging Flow Rate**: Use SQS batching and concurrency controls defined in [infrastructure/sqs/main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/sqs/main.tf) to decouple workloads and smooth ingestion spikes.


### Key Files
- All directories under [infrastructure/](file:///d:/Git/Boardgame-Recommender/infrastructure/) (e.g. [lambda/](file:///d:/Git/Boardgame-Recommender/infrastructure/lambda/), [s3/](file:///d:/Git/Boardgame-Recommender/infrastructure/s3/), [iam/](file:///d:/Git/Boardgame-Recommender/infrastructure/iam/), [main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/main.tf)).
- [ecr_infrastructure/](file:///d:/Git/Boardgame-Recommender/ecr_infrastructure/)
