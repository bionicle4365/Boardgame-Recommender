data "aws_ssm_parameter" "bgg_game_data_scraper_ecr_url" {
  name = "/bgg/ecr/bgg_game_data_scraper_repository_url"
}

resource "aws_lambda_function" "bgg_game_data_scraper" {
  function_name                  = var.data_lambda_function_name
  role                           = var.lambda_execution_role_arn
  package_type                   = "Image"
  image_uri                      = "${data.aws_ssm_parameter.bgg_game_data_scraper_ecr_url.value}:latest"
  timeout                        = 180
  memory_size                    = 256
  reserved_concurrent_executions = var.data_lambda_concurrency_limit

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = "boardgame-app"
      BGG_API_TOKEN         = var.bgg_api_token
      PYTHONIOENCODING      = "utf-8"
    }
  }
}

resource "aws_lambda_event_source_mapping" "bgg_game_data_scraper_esm" {
  event_source_arn = var.data_sqs_queue_arn
  function_name    = aws_lambda_function.bgg_game_data_scraper.arn
  enabled          = true
  # 100 IDs are fetched in a SINGLE BGG API call (?id=1,2,...,100&stats=1).
  # This is the primary throughput lever: 10x fewer Lambda invocations vs batch_size=10.
  # Upper bound is determined by Lambda timeout vs sequential S3 write time (~300ms each):
  #   100 games x 300ms = 30s S3 writes + ~5s API = ~35s total (well under 180s timeout).
  batch_size = 100
  # AWS requires this to be > 0 when batch_size > 10. With 60k messages in the
  # queue the batch fills to 100 almost instantly so this doesn't affect throughput.
  maximum_batching_window_in_seconds = 30
  function_response_types            = ["ReportBatchItemFailures"]
}

data "aws_ssm_parameter" "bgg_user_data_scraper_ecr_url" {
  name = "/bgg/ecr/bgg_user_data_scraper_repository_url"
}

resource "aws_lambda_function" "bgg_user_data_scraper" {
  function_name                  = var.user_lambda_function_name
  role                           = var.lambda_execution_role_arn
  package_type                   = "Image"
  image_uri                      = "${data.aws_ssm_parameter.bgg_user_data_scraper_ecr_url.value}:latest"
  timeout                        = 120
  memory_size                    = 256
  reserved_concurrent_executions = var.user_lambda_concurrency_limit

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = "boardgame-app"
      BGG_API_TOKEN         = var.bgg_api_token
      PYTHONIOENCODING      = "utf-8"
    }
  }
}

resource "aws_lambda_event_source_mapping" "bgg_user_data_scraper_esm" {
  event_source_arn        = var.user_sqs_queue_arn
  function_name           = aws_lambda_function.bgg_user_data_scraper.arn
  enabled                 = true
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

data "archive_file" "bgg_api_proxy_zip" {
  type        = "zip"
  source_file = "../bgg_api_proxy/bgg_api_proxy.py"
  output_path = "${path.module}/bgg_api_proxy.zip"
}

resource "aws_lambda_function" "bgg_api_proxy" {
  filename         = data.archive_file.bgg_api_proxy_zip.output_path
  function_name    = "bgg_api_proxy"
  role             = var.lambda_execution_role_arn
  handler          = "bgg_api_proxy.lambda_handler"
  source_code_hash = data.archive_file.bgg_api_proxy_zip.output_base64sha256
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128

  environment {
    variables = {
      BGG_API_TOKEN = var.bgg_api_token
    }
  }
}

data "aws_ssm_parameter" "bgg_recommender_ecr_url" {
  name = "/bgg/ecr/bgg_recommender_repository_url"
}

data "aws_ssm_parameter" "bgg_compactor_ecr_url" {
  name = "/bgg/ecr/bgg_compactor_repository_url"
}

resource "aws_lambda_function" "bgg_recommender" {
  function_name = "bgg_recommender"
  role          = var.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.aws_ssm_parameter.bgg_recommender_ecr_url.value}:latest"
  timeout       = 120
  memory_size   = 1024

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = var.s3_bucket_name
      USER_SQS_QUEUE_URL    = var.user_sqs_queue_url
      BEDROCK_MODEL_ID      = "amazon.nova-micro-v1:0"
      BGG_API_TOKEN         = var.bgg_api_token
      PYTHONIOENCODING      = "utf-8"
    }
  }

  # Image deployments are handled by GitHub Actions (update-function-code).
  # Terraform manages infrastructure config only, not the active image tag.
  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_function" "bgg_compactor" {
  function_name = "bgg_compactor"
  role          = var.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.aws_ssm_parameter.bgg_compactor_ecr_url.value}:latest"
  timeout       = 900
  memory_size   = 3008

  environment {
    variables = {
      S3_BUCKET_NAME   = var.s3_bucket_name
      PYTHONIOENCODING = "utf-8"
    }
  }

  # Image deployments are handled by GitHub Actions (update-function-code).
  # Terraform manages infrastructure config only, not the active image tag.
  lifecycle {
    ignore_changes = [image_uri]
  }
}

data "archive_file" "bgg_preferences_zip" {
  type        = "zip"
  source_file = "../bgg_preferences/bgg_preferences_handler.py"
  output_path = "${path.module}/bgg_preferences.zip"
}

resource "aws_lambda_function" "bgg_preferences" {
  filename         = data.archive_file.bgg_preferences_zip.output_path
  function_name    = "bgg_preferences"
  role             = var.lambda_execution_role_arn
  handler          = "bgg_preferences_handler.lambda_handler"
  source_code_hash = data.archive_file.bgg_preferences_zip.output_base64sha256
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = var.dynamodb_table_name
      USER_SQS_QUEUE_URL  = var.user_sqs_queue_url
    }
  }
}

data "aws_ssm_parameter" "bgg_taste_analytics_ecr_url" {
  name = "/bgg/ecr/bgg_taste_analytics_repository_url"
}

resource "aws_lambda_function" "bgg_taste_analytics" {
  function_name = "bgg_taste_analytics"
  role          = var.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.aws_ssm_parameter.bgg_taste_analytics_ecr_url.value}:latest"
  timeout       = 120
  memory_size   = 1024

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = var.s3_bucket_name
      PYTHONIOENCODING      = "utf-8"
    }
  }

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_event_source_mapping" "bgg_taste_analytics_esm" {
  event_source_arn        = var.taste_analytics_sqs_queue_arn
  function_name           = aws_lambda_function.bgg_taste_analytics.arn
  enabled                 = true
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}
