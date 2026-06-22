output "bgg_game_data_scraper_lambda_timeout" {
  value = aws_lambda_function.bgg_game_data_scraper.timeout
}
output "bgg_user_data_scraper_lambda_timeout" {
  value = aws_lambda_function.bgg_user_data_scraper.timeout
}

output "bgg_api_proxy_arn" {
  value = aws_lambda_function.bgg_api_proxy.arn
}

output "bgg_api_proxy_function_name" {
  value = aws_lambda_function.bgg_api_proxy.function_name
}

output "bgg_recommender_arn" {
  value = aws_lambda_function.bgg_recommender.arn
}

output "bgg_recommender_function_name" {
  value = aws_lambda_function.bgg_recommender.function_name
}

output "bgg_compactor_arn" {
  value = aws_lambda_function.bgg_compactor.arn
}

output "bgg_compactor_function_name" {
  value = aws_lambda_function.bgg_compactor.function_name
}

output "bgg_preferences_arn" {
  value = aws_lambda_function.bgg_preferences.arn
}

output "bgg_preferences_function_name" {
  value = aws_lambda_function.bgg_preferences.function_name
}