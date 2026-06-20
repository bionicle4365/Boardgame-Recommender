resource "aws_sqs_queue" "bgg_game_data_scraper_queue" {
  name = var.data_sqs_queue_name
  # AWS recommends visibility_timeout >= 6x Lambda timeout for batched processing.
  # With batch_size=10 and reserved_concurrency=2, messages can wait for a Lambda slot.
  visibility_timeout_seconds = var.data_sqs_queue_visibility_timeout_seconds * 6
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bgg_game_data_scraper_deadletter.arn
    # 10 retries: allows for throttling bursts without prematurely DLQ-ing
    maxReceiveCount = 10
  })
}

resource "aws_sqs_queue" "bgg_game_data_scraper_deadletter" {
  name = "${var.data_sqs_queue_name}_deadletter"
}

resource "aws_sqs_queue" "bgg_user_data_scraper_queue" {
  name                       = var.user_sqs_queue_name
  visibility_timeout_seconds = var.user_sqs_queue_visibility_timeout_seconds
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bgg_user_data_scraper_deadletter.arn
    maxReceiveCount     = 10
  })
}

resource "aws_sqs_queue" "bgg_user_data_scraper_deadletter" {
  name = "${var.user_sqs_queue_name}_deadletter"
}