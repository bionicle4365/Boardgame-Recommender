variable "glue_database_name" {
  description = "The name of the Glue database"
  type        = string
}

variable "glue_raw_table_name" {
  description = "The name of the Glue raw table"
  type        = string
}

variable "glue_combined_table_name" {
  description = "The name of the Glue combined table"
  type        = string
  
}

variable "combine_glue_job_name" {
  description = "The name of the Glue job for combining raw data"
  type        = string
}

variable "combine_glue_job_script_key" {
  description = "The S3 location of the Glue job script for combining raw data"
  type        = string
}

variable "glue_service_role_arn" {
  description = "The ARN of the Glue service role"
  type        = string
}

variable "glue_user_raw_table_name" {
  description = "The name of the Glue user raw table"
  type        = string
}