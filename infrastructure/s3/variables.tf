variable "s3_bucket_name" {
  description = "The name of the S3 bucket"
  type        = string
  default     = "boardgame-app"
}

variable "combine_glue_job_script_name" {
  description = "The name of the Glue job script"
  type        = string
  default     = "combine_raw_to_single_file.py"
}

variable "taste_analytics_sqs_queue_arn" {
  description = "The ARN of the SQS queue for taste analytics"
  type        = string
}