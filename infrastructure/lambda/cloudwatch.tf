resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset([
    aws_lambda_function.bgg_game_data_scraper.function_name,
    aws_lambda_function.bgg_user_data_scraper.function_name,
    aws_lambda_function.bgg_api_proxy.function_name,
    aws_lambda_function.bgg_recommender.function_name,
    aws_lambda_function.bgg_compactor.function_name
  ])

  alarm_name          = "${each.key}-errors-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Alarm when Lambda function ${each.key} registers errors"
  actions_enabled     = false

  dimensions = {
    FunctionName = each.key
  }
}
