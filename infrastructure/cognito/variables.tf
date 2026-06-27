variable "ses_source_arn" {
  description = "The ARN of the verified SES identity"
  type        = string
}

variable "ses_from_email_address" {
  description = "The FROM email address to use for Cognito emails"
  type        = string
}
