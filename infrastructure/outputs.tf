output "domain_verification_record_name" {
  value = module.ses.domain_verification_record_name
}

output "domain_verification_record_type" {
  value = module.ses.domain_verification_record_type
}

output "domain_verification_record_value" {
  value = module.ses.domain_verification_record_value
}

output "dkim_cname_records" {
  description = "The CNAME records to add for DKIM verification"
  value       = module.ses.dkim_cname_records
}
