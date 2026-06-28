data "aws_s3_bucket" "boardgame_app_bucket" {
  bucket = var.s3_bucket_name
}

resource "aws_s3_bucket_notification" "taste_analytics_notification" {
  bucket = data.aws_s3_bucket.boardgame_app_bucket.id

  queue {
    queue_arn     = var.taste_analytics_sqs_queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "data/users/"
    filter_suffix = ".parquet"
  }
}

# resource "aws_s3_object" "boardgame_app_combine_script" {
#   bucket = data.aws_s3_bucket.boardgame_app_bucket.id
#   key    = "scripts/${var.combine_glue_job_script_name}"
#   source = "../bgg_raw_to_compressed/${var.combine_glue_job_script_name}"
#   etag   = filemd5("../bgg_raw_to_compressed/${var.combine_glue_job_script_name}")
# }

resource "aws_s3_object" "active_previews_json" {
  bucket = data.aws_s3_bucket.boardgame_app_bucket.id
  key    = "data/active_previews.json"
  source = "${path.module}/../../data/active_previews.json"
  etag   = filemd5("${path.module}/../../data/active_previews.json")
}


