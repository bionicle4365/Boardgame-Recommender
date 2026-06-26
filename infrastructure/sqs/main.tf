resource "aws_sqs_queue" "bgg_game_data_scraper_queue" {
  name = var.data_sqs_queue_name
  # AWS recommends visibility_timeout >= 6x Lambda timeout for batched processing.
  # With batch_size=100 and reserved_concurrency=2, messages can wait for a Lambda slot.
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

resource "aws_sqs_queue" "taste_analytics_deadletter" {
  name = "taste_analytics_dlq"
}

resource "aws_sqs_queue" "taste_analytics_queue" {
  name                       = "taste_analytics_queue"
  visibility_timeout_seconds = 720 # 6x Lambda timeout (120s)
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.taste_analytics_deadletter.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_policy" "taste_analytics_queue_policy" {
  queue_url = aws_sqs_queue.taste_analytics_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.taste_analytics_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = var.s3_bucket_arn
          }
        }
      }
    ]
  })
}