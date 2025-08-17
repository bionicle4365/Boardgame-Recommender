data "aws_s3_bucket" "boardgame_app_bucket" {
  bucket = "boardgame-app"
}

resource "aws_glue_catalog_database" "boardgame_app_db" {
  name = var.glue_database_name
}

resource "aws_glue_catalog_table" "boardgame_app_table" {
  name          = var.glue_table_name
  database_name = aws_glue_catalog_database.boardgame_app_db.name

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.boardgame_app_bucket.id}/data/boardgames/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    compressed    = false
    ser_de_info {
      name                  = "boardgame_app_parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "parquet.ignore.statistics" = "true"
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
    }

    columns {
      name = "mechanics"
    }

    columns {
      name = "designers"
    }

    columns {
      name = "artists"
    }

    columns {
      name = "publishers"
    }

    columns {
      name = "families"
    }
    
  }
}