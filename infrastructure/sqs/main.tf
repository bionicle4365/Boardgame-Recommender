resource "aws_sqs_queue" "bgg_game_data_scraper_queue" {
  name = var.sqs_queue_name
  visibility_timeout_seconds = var.sqs_queue_visibility_timeout_seconds
}