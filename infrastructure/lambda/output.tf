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