output "data_sqs_queue_url" {
  description = "The URL of the SQS queue for the BGG game data scraper"
  value       = aws_sqs_queue.bgg_game_data_scraper_queue.id
}
output "data_sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG game data scraper"
  value       = aws_sqs_queue.bgg_game_data_scraper_queue.arn
}
output "data_sqs_queue_name" {
  description = "The name of the SQS queue for the BGG game data scraper"
  value       = aws_sqs_queue.bgg_game_data_scraper_queue.name
}
output "user_sqs_queue_url" {
  description = "The URL of the SQS queue for the BGG user data scraper"
  value       = aws_sqs_queue.bgg_user_data_scraper_queue.id
}
output "user_sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG user data scraper"
  value       = aws_sqs_queue.bgg_user_data_scraper_queue.arn
}

output "taste_analytics_sqs_queue_arn" {
  description = "The ARN of the taste analytics SQS queue"
  value       = aws_sqs_queue.taste_analytics_queue.arn
}