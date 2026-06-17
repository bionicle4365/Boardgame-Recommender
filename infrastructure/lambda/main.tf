data "aws_ssm_parameter" "bgg_game_data_scraper_ecr_url" {
  name = "/bgg/ecr/bgg_game_data_scraper_repository_url"
}

resource "aws_lambda_function" "bgg_game_data_scraper" {
  function_name    = var.data_lambda_function_name
  role             = var.lambda_execution_role_arn
  package_type     = "Image"
  image_uri        = "${data.aws_ssm_parameter.bgg_game_data_scraper_ecr_url.value}:latest"
  timeout          = 120
  memory_size      = 256

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = "boardgame-app"
      BGG_API_TOKEN         = var.bgg_api_token
    }
  }
}

resource "aws_lambda_event_source_mapping" "bgg_game_data_scraper_esm" {
  event_source_arn = var.data_sqs_queue_arn
  function_name    = aws_lambda_function.bgg_game_data_scraper.arn
  enabled          = true
  batch_size       = 10
}

data "aws_ssm_parameter" "bgg_user_data_scraper_ecr_url" {
  name = "/bgg/ecr/bgg_user_data_scraper_repository_url"
}

resource "aws_lambda_function" "bgg_user_data_scraper" {
  function_name    = var.user_lambda_function_name
  role             = var.lambda_execution_role_arn
  package_type     = "Image"
  image_uri        = "${data.aws_ssm_parameter.bgg_user_data_scraper_ecr_url.value}:latest"
  timeout          = 120
  memory_size      = 256

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = "boardgame-app"
      BGG_API_TOKEN         = var.bgg_api_token
    }
  }
}

resource "aws_lambda_event_source_mapping" "bgg_user_data_scraper_esm" {
  event_source_arn = var.user_sqs_queue_arn
  function_name    = aws_lambda_function.bgg_user_data_scraper.arn
  enabled          = true
  batch_size       = 10
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
  runtime          = "python3.10"
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

resource "aws_lambda_function" "bgg_recommender" {
  function_name = "bgg_recommender"
  role          = var.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.aws_ssm_parameter.bgg_recommender_ecr_url.value}:latest"
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      S3_OUTPUT_BUCKET_NAME = var.s3_bucket_name
      USER_SQS_QUEUE_URL    = var.user_sqs_queue_url
      BEDROCK_MODEL_ID      = "anthropic.claude-3-haiku-20240307-v1:0"
    }
  }
}