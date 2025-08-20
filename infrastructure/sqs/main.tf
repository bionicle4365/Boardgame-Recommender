resource "aws_sqs_queue" "bgg_game_data_scraper_queue" {
  name = var.data_sqs_queue_name
  visibility_timeout_seconds = var.data_sqs_queue_visibility_timeout_seconds
}
resource "aws_sqs_queue" "bgg_user_data_scraper_queue" {
  name = var.user_sqs_queue_name
  visibility_timeout_seconds = var.user_sqs_queue_visibility_timeout_seconds
}