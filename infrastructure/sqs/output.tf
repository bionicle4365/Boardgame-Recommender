output "sqs_queue_url" {
  description = "The URL of the SQS queue for the BGG game data scraper"
  value       = aws_sqs_queue.bgg_game_data_scraper_queue.id
}
output "sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG game data scraper"
  value       = aws_sqs_queue.bgg_game_data_scraper_queue.arn
}
output "user_sqs_queue_url" {
  description = "The URL of the SQS queue for the BGG user data scraper"
  value       = aws_sqs_queue.bgg_user_data_scraper_queue.id
}
output "user_sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG user data scraper"
  value       = aws_sqs_queue.bgg_user_data_scraper_queue.arn
}