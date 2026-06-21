import os
import pyarrow.dataset as ds
import pyarrow.fs as fs
import pyarrow.parquet as pq

# Initialize Structured Logging with AWS Lambda Powertools or Fallback
try:
    from aws_lambda_powertools import Logger
    logger = Logger(service="bgg-compactor")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    class FallbackLogger:
        def __init__(self):
            self.log = logging.getLogger("bgg-compactor")
        def info(self, msg, *args, **kwargs):
            extra = kwargs.get('extra')
            if extra:
                self.log.info(f"{msg} - Extra: {extra}")
            else:
                self.log.info(msg)
        def error(self, msg, *args, **kwargs):
            extra = kwargs.get('extra')
            if extra:
                self.log.error(f"{msg} - Extra: {extra}")
            else:
                self.log.error(msg)
        def warning(self, msg, *args, **kwargs):
            extra = kwargs.get('extra')
            if extra:
                self.log.warning(f"{msg} - Extra: {extra}")
            else:
                self.log.warning(msg)
        def inject_lambda_context(self, func):
            return func
    logger = FallbackLogger()

@logger.inject_lambda_context
def lambda_handler(event, context):
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    raw_prefix = os.environ.get('RAW_PREFIX', 'data/boardgames/')
    combined_prefix = os.environ.get('COMBINED_PREFIX', 'data/boardgames_combined/')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    
    logger.info("Starting serverless S3 Parquet compaction", extra={
        "bucket_name": bucket_name,
        "raw_prefix": raw_prefix,
        "combined_prefix": combined_prefix
    })
    
    try:
        # Initialize PyArrow S3 filesystem
        s3_fs = fs.S3FileSystem(region=aws_region)
        
        # Define target schema to unify old (9-column) and new (20-column) Parquet files
        import pyarrow as pa
        target_schema = pa.schema([
            ('id', pa.string()),
            ('type', pa.string()),
            ('name', pa.string()),
            ('year_published', pa.int32()),
            ('min_players', pa.int32()),
            ('max_players', pa.int32()),
            ('playing_time', pa.int32()),
            ('min_playtime', pa.int32()),
            ('max_playtime', pa.int32()),
            ('min_age', pa.int32()),
            ('rating', pa.float64()),
            ('complexity', pa.float64()),
            ('thumbnail', pa.string()),
            ('image', pa.string()),
            ('categories', pa.list_(pa.string())),
            ('mechanics', pa.list_(pa.string())),
            ('designers', pa.list_(pa.string())),
            ('publishers', pa.list_(pa.string())),
            ('suggested_players_best', pa.list_(pa.string())),
            ('suggested_players_recommended', pa.list_(pa.string()))
        ])

        # Read all parquet files under the raw prefix in S3 directly using PyArrow Dataset API
        source_path = f"{bucket_name}/{raw_prefix}"
        logger.info(f"Reading all raw Parquet files from {source_path}")
        dataset = ds.dataset(source_path, format="parquet", filesystem=s3_fs, schema=target_schema)
        
        # Convert dataset to a PyArrow Table (in-memory merge)
        logger.info("Converting dataset to PyArrow Table")
        table = dataset.to_table()
        logger.info("Merge complete", extra={
            "num_rows": table.num_rows,
            "num_columns": table.num_columns
        })
        
        # Define output path
        output_file_path = f"{bucket_name}/{combined_prefix}catalog.parquet"
        logger.info(f"Writing Snappy-compressed combined Parquet file to s3://{output_file_path}")
        
        # Write back to S3 as a single snappy-compressed Parquet file
        pq.write_table(table, output_file_path, filesystem=s3_fs, compression="snappy")
        logger.info("S3 Parquet compaction completed successfully")
        
        return {
            'statusCode': 200,
            'body': f"Successfully compacted {table.num_rows} records into catalog.parquet"
        }
        
    except Exception as e:
        logger.error("CRITICAL ERROR during compaction", extra={"error": str(e)})
        return {
            'statusCode': 500,
            'body': f"Compaction failed: {str(e)}"
        }

if __name__ == '__main__':
    # Local debugging
    os.environ['S3_BUCKET_NAME'] = 'boardgame-app'
    lambda_handler({}, None)
