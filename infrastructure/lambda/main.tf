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