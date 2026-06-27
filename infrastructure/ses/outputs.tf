output "ses_domain_identity_arn" {
  description = "The ARN of the SES domain identity"
  value       = aws_ses_domain_identity.boardgame_app.arn
}

output "domain_verification_record_name" {
  value = "_amazonses.${aws_ses_domain_identity.boardgame_app.domain}"
}

output "domain_verification_record_type" {
  value = "TXT"
}

output "domain_verification_record_value" {
  value = aws_ses_domain_identity.boardgame_app.verification_token
}

output "dkim_cname_records" {
  description = "The CNAME records to add for DKIM verification"
  value = [
    for token in aws_ses_domain_dkim.boardgame_app.dkim_tokens : {
      name  = "${token}._domainkey.${aws_ses_domain_identity.boardgame_app.domain}"
      type  = "CNAME"
      value = "${token}.dkim.amazonses.com"
    }
  ]
}
