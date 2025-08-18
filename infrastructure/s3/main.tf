data "aws_s3_bucket" "boardgame_app_bucket" {
  bucket = var.s3_bucket_name
}

resource "aws_s3_object" "boardgame_app_combine_script" {
  bucket = data.aws_s3_bucket.boardgame_app_bucket.id
  key    = "scripts/${var.combine_glue_job_script_name}"
  source = "../bgg_raw_to_compressed/${var.combine_glue_job_script_name}"
  etag   = filemd5("../bgg_raw_to_compressed/${var.combine_glue_job_script_name}")
}