variable "data_sqs_queue_url" {
  description = "The URL of the SQS queue for the BGG game data scraper"
  type        = string
}
variable "data_sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG game data scraper"
  type        = string
}
variable "user_sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG user data scraper"
  type        = string
}
variable "data_lambda_function_name" {
  description = "The name of the Lambda function for the BGG game data scraper"
  type        = string
}
variable "lambda_execution_role_arn" {
  description = "The ARN of the IAM role for the Lambda function"
  type        = string
}
variable "user_lambda_function_name" {
  description = "The name of the Lambda function for the BGG game data scraper"
  type        = string
}

variable "user_sqs_queue_url" {
  description = "The URL of the SQS queue for the BGG user data scraper"
  type        = string
}

variable "s3_bucket_name" {
  description = "The name of the S3 bucket where scraper data is stored"
  type        = string
}

variable "bgg_api_token" {
  description = "The authorization token for the BGG API"
  type        = string
  default     = ""
  sensitive   = true
}

variable "data_lambda_concurrency_limit" {
  description = "Reserved concurrent executions limit for the game data scraper Lambda"
  type        = number
  default     = 2
}

variable "user_lambda_concurrency_limit" {
  description = "Reserved concurrent executions limit for the user collection scraper Lambda"
  type        = number
  default     = 2
}

variable "dynamodb_table_name" {
  description = "The name of the DynamoDB table for user preferences"
  type        = string
}

variable "taste_analytics_sqs_queue_arn" {
  description = "The ARN of the SQS queue for the BGG taste analytics"
  type        = string
}