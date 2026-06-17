# 1. Create the EventBridge Rule for a daily schedule (e.g., Midnight UTC)
resource "aws_cloudwatch_event_rule" "daily_bgg_scraper_schedule" {
  name                = "daily-bgg-scraper-schedule"
  description         = "Runs the BGG Discovery Scraper every day at midnight"
  schedule_expression = "cron(0 0 * * ? *)" 
}

# 2. Define the Target (What to trigger) - In this case, your ECS Fargate Task
resource "aws_cloudwatch_event_target" "run_bgg_scraper_task" {
  target_id = "run-bgg-scraper-ecs-task"
  rule      = aws_cloudwatch_event_rule.daily_bgg_scraper_schedule.name
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.eventbridge_ecs_execution_role.arn # Role allowing EventBridge to run tasks

  ecs_target {
    task_definition_arn = var.ecs_task_definition_arn
    task_count          = 1
    launch_type         = "FARGATE"
    
    network_configuration {
      subnets          = var.ecs_subnets
      security_groups  = [var.ecs_security_group_id]
      assign_public_ip = true # Set to true if using public subnets, false if private with NAT Gateway
    }
  }
}

# 3. IAM Role for EventBridge to invoke ECS
resource "aws_iam_role" "eventbridge_ecs_execution_role" {
  name = "eventbridge-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_ecs_execution_policy" {
  name = "eventbridge-ecs-execution-policy"
  role = aws_iam_role.eventbridge_ecs_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "ecs:RunTask"
        Resource = var.ecs_task_definition_arn
      },
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          var.ecs_task_execution_role_arn,
          var.ecs_task_role_arn
        ]
      }
    ]
  })
}
