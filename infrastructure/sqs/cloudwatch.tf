resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  for_each = toset([
    aws_sqs_queue.bgg_game_data_scraper_deadletter.name,
    aws_sqs_queue.bgg_user_data_scraper_deadletter.name,
    aws_sqs_queue.taste_analytics_deadletter.name
  ])

  alarm_name          = "${each.key}-messages-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300 # 5 minutes
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Alarm when SQS DLQ ${each.key} has visible messages"
  actions_enabled     = false

  dimensions = {
    QueueName = each.key
  }
}
