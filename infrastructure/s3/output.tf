output "combine_glue_job_script_key" {
  value = aws_s3_object.boardgame_app_combine_script.key
}

output "bucket_name" {
  value = data.aws_s3_bucket.boardgame_app_bucket.bucket
}

output "bucket_arn" {
  value = data.aws_s3_bucket.boardgame_app_bucket.arn
}
