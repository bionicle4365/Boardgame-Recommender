resource "aws_sqs_queue" "bgg_game_data_scraper_queue" {
  name = var.sqs_queue_name
}