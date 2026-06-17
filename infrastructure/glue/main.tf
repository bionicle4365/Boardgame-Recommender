data "aws_s3_bucket" "boardgame_app_bucket" {
  bucket = "boardgame-app"
}

resource "aws_glue_catalog_database" "boardgame_app_db" {
  name = var.glue_database_name
}

resource "aws_glue_catalog_table" "boardgame_app_table_raw" {
  name          = var.glue_raw_table_name
  database_name = aws_glue_catalog_database.boardgame_app_db.name
  parameters    = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/data/boardgames/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    compressed    = false
    ser_de_info {
      name                  = "boardgame_app_parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "parquet"
      }
    }

    columns {
        name = "id"
        type = "string"
    }

    columns {
        name = "name"
        type = "string"
    }

    columns {
        name = "max_players"
        type = "int"
    }

    columns {
        name = "rating"
        type = "double"
    }

    columns {
        name = "categories"
        type = "array<string>"
    }

    columns {
        name = "mechanics"
        type = "array<string>"
    }

    columns {
        name = "designers"
        type = "array<string>"
    }

    columns {
        name = "year_published"
        type = "int"
    }
    
  }
}

resource "aws_glue_crawler" "boardgame_app_raw_game_data_crawler" {
  name          = "boardgame-app-raw-game-data-crawler"
  database_name = aws_glue_catalog_database.boardgame_app_db.name
  role          = var.glue_service_role_arn

  s3_target {
    path = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/data/boardgames/"
  }

  # This configuration helps the crawler update the existing table gracefully.
  configuration = jsonencode({
    "Version" : 1.0,
    "CrawlerOutput" : {
      "Partitions" : { "AddOrUpdateBehavior" : "InheritFromTable" },
      "Tables" : { "AddOrUpdateBehavior" : "MergeNewColumns" }
    }
  })
}

resource "aws_glue_job" "boardgame_app_combine_job" {
  name              = var.combine_glue_job_name
  description       = "Glue job to combine raw board game data into a single Parquet file"
  role_arn          = var.glue_service_role_arn
  glue_version      = "5.0"
  max_retries       = 0
  timeout           = 15
  number_of_workers = 2
  worker_type       = "G.1X"
  execution_class   = "FLEX"

  command {
    name            = "glueetl"
    script_location = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/${var.combine_glue_job_script_key}"
    python_version  = "3"
  }

  default_arguments = {
    "--TempDir" = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/temp/"
    "--job-language" = "python"
    "--enable-metrics" = "true"
    "--enable-job-insights" = "true"
    "--enable-glue-datacatalog" = "true"
    "--enable-spark-ui" = "true"
  }
}

resource "aws_glue_catalog_table" "boardgame_app_table_combined" {
  name          = var.glue_combined_table_name
  database_name = aws_glue_catalog_database.boardgame_app_db.name
  parameters    = {
    "classification" = "parquet"
    "parquet.compression" = "SNAPPY"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/data/boardgames_combined/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    compressed    = false
    ser_de_info {
      name                  = "boardgame_app_parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "parquet"
      }
    }

    columns {
        name = "id"
        type = "string"
    }

    columns {
        name = "name"
        type = "string"
    }

    columns {
        name = "max_players"
        type = "int"
    }

    columns {
        name = "rating"
        type = "double"
    }

    columns {
        name = "categories"
        type = "array<string>"
    }

    columns {
        name = "mechanics"
        type = "array<string>"
    }

    columns {
        name = "designers"
        type = "array<string>"
    }

    columns {
        name = "year_published"
        type = "int"
    }
  }
}

resource "aws_glue_crawler" "boardgame_app_user_data_crawler" {
  name          = "boardgame-app-user-data-crawler"
  database_name = aws_glue_catalog_database.boardgame_app_db.name
  role          = var.glue_service_role_arn

  s3_target {
    path = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/data/users/"
  }

  configuration = jsonencode({
    "Version" : 1.0,
    "CrawlerOutput" : {
      "Partitions" : { "AddOrUpdateBehavior" : "InheritFromTable" },
      "Tables" : { "AddOrUpdateBehavior" : "MergeNewColumns" }
    }
  })
}

resource "aws_glue_catalog_table" "boardgame_app_user_table_raw" {
  name          = var.glue_user_raw_table_name
  database_name = aws_glue_catalog_database.boardgame_app_db.name
  parameters    = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/data/users/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    compressed    = false
    ser_de_info {
      name                  = "boardgame_app_parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "parquet"
      }
    }

    columns {
        name = "id"
        type = "string"
    }

    columns {
        name = "username"
        type = "string"
    }

    columns {
        name = "rating"
        type = "double"
    }

    columns {
        name = "own"
        type = "boolean"
    }
  }
}

resource "aws_glue_workflow" "boardgame_workflow" {
  name        = "boardgame-data-workflow"
  description = "Workflow to coordinate crawler runs and data compaction ETL jobs"
}

resource "aws_glue_trigger" "start_crawler" {
  name          = "start-crawler-trigger"
  type          = "SCHEDULED"
  schedule      = "cron(0 2 ? * SUN *)"
  workflow_name = aws_glue_workflow.boardgame_workflow.name

  actions {
    crawler_name = aws_glue_crawler.boardgame_app_raw_game_data_crawler.name
  }
}

resource "aws_glue_trigger" "run_compaction_job" {
  name          = "run-compaction-job-trigger"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.boardgame_workflow.name

  predicate {
    logical = "ANY"
    conditions {
      crawler_name = aws_glue_crawler.boardgame_app_raw_game_data_crawler.name
      crawl_state  = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.boardgame_app_combine_job.name
  }
}