# Infrastructure Rules (`infrastructure/`)

- **No Direct Applies or Image Pushes**: Never execute `terraform apply` or build/push Docker images directly. Use `terraform -chdir=infrastructure fmt -check` and `terraform -chdir=infrastructure validate` locally; deployments run via GitHub Actions.
- **Least-Privilege IAM**: Scope all IAM role policies to the exact resources and actions needed.
- **Serverless Cost Guardrails**: Preserve API Gateway rate limits (`throttling_rate_limit`, `throttling_burst_limit`), Lambda `reserved_concurrent_executions`, low timeouts, and PyArrow Lambda compaction (never re-enable Glue crawlers or Athena).
- **Contract Sync**: Any new or modified API Gateway route in `infrastructure/apigateway/main.tf` must also be updated in `docs/contracts/schemas_and_routes.json`.
