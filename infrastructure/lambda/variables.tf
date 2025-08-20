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