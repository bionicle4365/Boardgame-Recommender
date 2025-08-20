data "aws_secretsmanager_secret" "bgg_game_data_scraper_ecr_url" {
  name = "bgg_game_data_scraper_repository_url"
}
data "aws_secretsmanager_secret_version" "data_current" {
  secret_id = data.aws_secretsmanager_secret.bgg_game_data_scraper_ecr_url.id
}

resource "aws_lambda_function" "bgg_game_data_scraper" {
  function_name    = var.data_lambda_function_name
  role             = var.lambda_execution_role_arn
  package_type     = "Image"
  image_uri        = "${data.aws_secretsmanager_secret_version.data_current.secret_string}:latest"
  timeout          = 120
  memory_size      = 256
}

resource "aws_lambda_event_source_mapping" "bgg_game_data_scraper_esm" {
  event_source_arn = var.data_sqs_queue_arn
  function_name    = aws_lambda_function.bgg_game_data_scraper.arn
  enabled          = true
  batch_size       = 10
}

data "aws_secretsmanager_secret" "bgg_user_data_scraper_ecr_url" {
  name = "bgg_user_data_scraper_repository_url"
}
data "aws_secretsmanager_secret_version" "user_current" {
  secret_id = data.aws_secretsmanager_secret.bgg_user_data_scraper_ecr_url.id
}

resource "aws_lambda_function" "bgg_user_data_scraper" {
  function_name    = var.user_lambda_function_name
  role             = var.lambda_execution_role_arn
  package_type     = "Image"
  image_uri        = "${data.aws_secretsmanager_secret_version.user_current.secret_string}:latest"
  timeout          = 120
  memory_size      = 256
}

resource "aws_lambda_event_source_mapping" "bgg_user_data_scraper_esm" {
  event_source_arn = var.user_sqs_queue_arn
  function_name    = aws_lambda_function.bgg_user_data_scraper.arn
  enabled          = true
  batch_size       = 10
}