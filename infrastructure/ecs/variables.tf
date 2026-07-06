variable "s3_bucket_name" {
  description = "The name of the S3 bucket where BGG scraper state is stored"
  type        = string
}

variable "s3_bucket_arn" {
  description = "The ARN of the S3 bucket where BGG scraper state is stored"
  type        = string
}

variable "sqs_queue_name" {
  description = "The name of the SQS queue for the BGG game data scraper"
  type        = string
}

variable "sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG game data scraper"
  type        = string
}

variable "bgg_api_token" {
  description = "The authorization token for the BGG API"
  type        = string
  default     = ""
  sensitive   = true
}

variable "bgg_game_scraper_ecr_url" {
  description = "The ECR repository URL for the BGG game scraper image"
  type        = string
}

