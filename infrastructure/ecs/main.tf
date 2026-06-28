# ECS Cluster
resource "aws_ecs_cluster" "scraper_cluster" {
  name = "bgg-scraper-cluster"
}

# IAM roles for ECS Tasks
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "bggScraperEcsTaskExecutionRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name = "bggScraperEcsTaskRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# Add any additional policies for the task role here (e.g. S3 access, SQS access)
resource "aws_iam_role_policy" "ecs_task_policy" {
  name = "bggScraperEcsTaskPolicy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = [
          "${var.s3_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl",
          "sqs:GetQueueAttributes"
        ]
        Resource = [
          var.sqs_queue_arn
        ]
      }
    ]
  })
}

# Fetch the ECR repository created in the ecr_infrastructure state
data "aws_ecr_repository" "bgg_game_scraper" {
  name = "bgg_game_scraper"
}

resource "aws_cloudwatch_log_group" "scraper_log_group" {
  name              = "/ecs/bgg-scraper-task"
  retention_in_days = 7
}

# Task Definition
resource "aws_ecs_task_definition" "scraper_task" {
  family                   = "bgg-scraper-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([{
    name      = "bgg-scraper-container"
    image     = "${data.aws_ecr_repository.bgg_game_scraper.repository_url}:latest"
    essential = true
    environment = [
      {
        name  = "S3_BUCKET_NAME"
        value = var.s3_bucket_name
      },
      {
        name  = "SQS_QUEUE_NAME"
        value = var.sqs_queue_name
      },
      {
        name  = "AWS_REGION"
        value = "us-east-1"
      },
      {
        name  = "BGG_API_TOKEN"
        value = var.bgg_api_token
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.scraper_log_group.name
        awslogs-region        = "us-east-1"
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

# Default VPC for Fargate Networking
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "scraper_sg" {
  name        = "bgg-scraper-sg"
  description = "Security group for BGG Scraper ECS tasks"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
