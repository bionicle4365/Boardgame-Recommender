output "lambda_exec_role_arn" {
  description = "The ARN of the IAM role for the Lambda function"
  value       = aws_iam_role.lambda_exec.arn
}

output "glue_service_role_arn" {
  description = "The ARN of the Glue service role"
  value       = aws_iam_role.glue_service_role.arn
}