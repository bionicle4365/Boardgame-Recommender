resource "aws_lambda_function" "bgg_game_data_scraper" {
  function_name    = var.lambda_function_name
  runtime          = "python3.10"
  handler          = "bgg_game_data_scraper.lambda_handler"
  role             = var.lambda_execution_role_arn
  timeout          = 300 # 5 minutes
  source_code_hash = filebase64sha256("bgg_game_data_scraper.zip")
  filename         = "bgg_game_data_scraper.zip"
}

resource "aws_lambda_event_source_mapping" "bgg_game_data_scraper_esm" {
  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.bgg_game_data_scraper.arn
  enabled          = true
}