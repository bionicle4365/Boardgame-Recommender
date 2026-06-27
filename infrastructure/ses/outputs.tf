output "ses_email_identity_arn" {
  description = "The ARN of the SES email identity"
  value       = aws_ses_email_identity.boardgame_app.arn
}

output "verified_email_address" {
  description = "The verified email address"
  value       = aws_ses_email_identity.boardgame_app.email
}
