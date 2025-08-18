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
        name = "type"
        type = "string"
    }

    columns {
        name = "name"
        type = "string"
    }

    columns {
        name = "year_published"
        type = "int"
    }

    columns {
        name = "min_players"
        type = "int"
    }

    columns {
        name = "max_players"
        type = "int"
    }

    columns {
        name = "playing_time"
        type = "int"
    }

    columns {
        name = "description"
        type = "string"
    }
    
    columns {
        name = "min_playtime"
        type = "int"
    }

    columns {
        name = "max_playtime"
        type = "int"
    }

    columns {
        name = "min_age"
        type = "int"
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
        name = "artists"
        type = "array<string>"
      }

    columns {
        name = "publishers"
        type = "array<string>"
      }

    columns {
        name = "families"
        type = "array<string>"
      }
    
  }
}

resource "aws_glue_job" "boardgame_app_combine_job" {
  name     = var.combine_glue_job_name
  description = "Glue job to combine raw board game data into a single Parquet file"
  role_arn = var.glue_service_role_arn
  glue_version      = "5.0"
  max_retries       = 0
  timeout           = 2
  number_of_workers = 2
  worker_type       = "G.1X"
  execution_class   = "STANDARD"

  command {
    name            = "combine_raw_to_single_file"
    script_location = var.combine_glue_job_script_key
    python_version  = "3"
  }

  default_arguments = {
    "--TempDir" = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/temp/"
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
        name = "type"
        type = "string"
    }

    columns {
        name = "name"
        type = "string"
    }

    columns {
        name = "year_published"
        type = "int"
    }

    columns {
        name = "min_players"
        type = "int"
    }

    columns {
        name = "max_players"
        type = "int"
    }

    columns {
        name = "playing_time"
        type = "int"
    }

    columns {
        name = "description"
        type = "string"
    }
    
    columns {
        name = "min_playtime"
        type = "int"
    }

    columns {
        name = "max_playtime"
        type = "int"
    }

    columns {
        name = "min_age"
        type = "int"
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
        name = "artists"
        type = "array<string>"
      }

    columns {
        name = "publishers"
        type = "array<string>"
      }

    columns {
        name = "families"
        type = "array<string>"
      }
    
  }
}