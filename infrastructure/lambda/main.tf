data "aws_secretsmanager_secret" "bgg_game_data_scraper_ecr_url" {
  name = "bgg_game_data_scraper_ecr_url"
}
data "aws_secretsmanager_secret_version" "current" {
  secret_id = data.aws_secretsmanager_secret.bgg_game_data_scraper_ecr_url.id
}

resource "aws_lambda_function" "bgg_game_data_scraper" {
  function_name    = var.lambda_function_name
  role             = var.lambda_execution_role_arn
  package_type     = "Image"
  image_uri        = "${data.aws_secretsmanager_secret_version.current.secret_string}:latest"
  timeout          = 120
}

resource "aws_lambda_event_source_mapping" "bgg_game_data_scraper_esm" {
  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.bgg_game_data_scraper.arn
  enabled          = true
}