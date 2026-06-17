variable "data_sqs_queue_name" {
  description = "The name of the SQS queue for the BGG game data scraper"
  type        = string
}
variable "data_sqs_queue_visibility_timeout_seconds" {
  description = "The visibility timeout for the SQS queue in seconds"
  type        = number
}
variable "user_sqs_queue_name" {
  description = "The name of the SQS queue for the BGG user data scraper"
  type        = string
}
variable "user_sqs_queue_visibility_timeout_seconds" {
  description = "The visibility timeout for the SQS queue in seconds"
  type        = number
}