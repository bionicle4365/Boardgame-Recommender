CREATE TABLE IF NOT EXISTS boardgame_app_combined_user_data
  WITH (format='PARQUET', parquet_compression = 'SNAPPY', external_location='s3://boardgame-app/data/users_combined') AS
SELECT
  *
FROM
  boardgame_app_user_raw_table