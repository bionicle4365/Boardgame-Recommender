CREATE TABLE IF NOT EXISTS boardgame_app_combined_game_data
  WITH (format='PARQUET', parquet_compression = 'SNAPPY', external_location='s3://boardgame-app/data/boardgames_combined') AS
SELECT
  *
FROM
  boardgame_app_raw_table