import os
import io
import pyarrow as pa
import pyarrow.parquet as pq
import boto3
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.config import Config

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

# Target schema to unify Parquet files
TARGET_SCHEMA = pa.schema([
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

def align_table_to_schema(table, target_schema):
    """
    Align a PyArrow Table's columns and types with a target schema.
    Missing fields are filled with nulls, and existing fields are cast to target types.
    """
    num_rows = table.num_rows
    arrays = []
    
    for field in target_schema:
        name = field.name
        target_type = field.type
        
        if name in table.column_names:
            col = table.column(name)
            if col.type == target_type:
                arrays.append(col)
            else:
                arrays.append(col.cast(target_type))
        else:
            arrays.append(pa.nulls(num_rows, type=target_type))
            
    return pa.Table.from_arrays(arrays, schema=target_schema)

def normalize_string_types(table):
    """
    Cast all large_string (large_utf8) columns to string (utf8).
    Different versions of pandas/pyarrow write the same string column as either
    string or large_string, causing pa.concat_tables to fail with type mismatch errors.
    """
    new_columns = []
    new_fields = []
    for i, field in enumerate(table.schema):
        col = table.column(i)
        if field.type == pa.large_string():
            col = col.cast(pa.string())
            field = pa.field(field.name, pa.string())
        new_columns.append(col)
        new_fields.append(field)
    return pa.Table.from_arrays(new_columns, schema=pa.schema(new_fields))

def download_and_parse(s3_client, bucket_name, key):
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        # Use with block to explicitly close the StreamingBody and return the connection to the pool
        with response['Body'] as stream:
            data = stream.read()
        reader = io.BytesIO(data)
        table = pq.read_table(reader)
        # Normalize string types to avoid large_string vs string concat failures
        table = normalize_string_types(table)
        return table
    except Exception as e:
        logger.error(f"Error parsing S3 object at {key}: {e}")
        return None

@logger.inject_lambda_context
def lambda_handler(event, context):
    # Event payload takes precedence over env vars, allowing EventBridge to
    # inject per-schedule config into a single shared Lambda function.
    bucket_name = event.get('s3_bucket_name') or os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    raw_prefix = event.get('raw_prefix') or os.environ.get('RAW_PREFIX', 'data/boardgames/')
    combined_prefix = event.get('combined_prefix') or os.environ.get('COMBINED_PREFIX', 'data/boardgames_combined/')
    output_filename = event.get('output_filename') or os.environ.get('OUTPUT_FILENAME', 'catalog.parquet')
    apply_schema_alignment_val = event.get('apply_schema_alignment')
    if apply_schema_alignment_val is None:
        apply_schema_alignment = os.environ.get('APPLY_SCHEMA_ALIGNMENT', 'true').lower() == 'true'
    else:
        apply_schema_alignment = bool(apply_schema_alignment_val)
    aws_region = event.get('aws_region') or os.environ.get('AWS_REGION', 'us-east-1')
    
    logger.info("Starting optimized multithreaded S3 Parquet compaction", extra={
        "bucket_name": bucket_name,
        "raw_prefix": raw_prefix,
        "combined_prefix": combined_prefix
    })
    
    try:
        # Configure custom connection pool size for boto3 to match ThreadPoolExecutor max_workers
        max_workers = 80
        config = Config(
            max_pool_connections=max_workers + 10,
            retries={'max_attempts': 5, 'mode': 'standard'}
        )
        s3_client = boto3.client('s3', region_name=aws_region, config=config)
        
        # Paginate S3 objects
        logger.info(f"Listing all raw Parquet files from {bucket_name}/{raw_prefix}")
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=raw_prefix)
        
        keys = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.endswith('.parquet') and not key.endswith(output_filename):
                        keys.append(key)
                        
        num_files = len(keys)
        logger.info(f"Found {num_files} raw Parquet files to compact.")
        
        if num_files == 0:
            return {
                'statusCode': 200,
                'body': "No files found to compact."
            }
            
        master_tables = []
        chunk_size = 10000
        
        logger.info(f"Downloading and merging {num_files} files in chunks of {chunk_size} using ThreadPoolExecutor with {max_workers} workers...", extra={
            "apply_schema_alignment": apply_schema_alignment,
            "output_filename": output_filename
        })
        
        for chunk_start in range(0, num_files, chunk_size):
            chunk_keys = keys[chunk_start:chunk_start + chunk_size]
            logger.info(f"Processing chunk {chunk_start // chunk_size + 1}: files {chunk_start} to {chunk_start + len(chunk_keys)}")
            
            chunk_tables = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_key = {
                    executor.submit(download_and_parse, s3_client, bucket_name, key): key
                    for key in chunk_keys
                }
                
                for future in as_completed(future_to_key):
                    key = future_to_key[future]
                    try:
                        table = future.result()
                        if table is not None:
                            # Apply game-catalog schema alignment only when configured
                            if apply_schema_alignment:
                                table = align_table_to_schema(table, TARGET_SCHEMA)
                            chunk_tables.append(table)
                    except Exception as e:
                        logger.error(f"Future execution failed for {key}: {e}")
            
            # Consolidate this chunk's tables immediately to release single-row table metadata memory
            if chunk_tables:
                # promote_options='default' resolves type mismatches (e.g. string vs large_string)
                # that arise from different pandas/pyarrow versions writing the same column differently.
                consolidated = pa.concat_tables(chunk_tables, promote_options='default')
                master_tables.append(consolidated)
                chunk_tables = []  # Clear references for garbage collection
                
        if not master_tables:
            raise ValueError("All raw Parquet file downloads and parses failed.")
            
        logger.info("Merging consolidated tables into final master table...")
        final_table = pa.concat_tables(master_tables, promote_options='default')
        
        logger.info("Merge complete", extra={
            "num_rows": final_table.num_rows,
            "num_columns": final_table.num_columns
        })
        
        # Write back to S3 as a single snappy-compressed Parquet file via /tmp to save RAM
        output_file_path = "/tmp/catalog.parquet"
        logger.info(f"Writing Snappy-compressed combined Parquet file to {output_file_path}")
        
        # Explicitly clear master_tables and force GC to free up memory before writing
        del master_tables
        gc.collect()
        
        pq.write_table(final_table, output_file_path, compression="snappy")
        
        # Upload using upload_file (highly memory efficient streaming from disk)
        logger.info(f"Uploading combined Parquet file to s3://{bucket_name}/{combined_prefix}{output_filename}")
        s3_client.upload_file(
            Filename=output_file_path,
            Bucket=bucket_name,
            Key=f"{combined_prefix}{output_filename}"
        )
        
        # Clean up local file
        if os.path.exists(output_file_path):
            os.remove(output_file_path)
            
        logger.info("S3 Parquet compaction completed successfully")
        
        return {
            'statusCode': 200,
            'body': f"Successfully compacted {final_table.num_rows} records into {output_filename}"
        }
        
    except Exception as e:
        logger.error("CRITICAL ERROR during compaction", extra={"error": str(e)})
        raise

if __name__ == '__main__':
    os.environ['S3_BUCKET_NAME'] = 'boardgame-app'
    lambda_handler({}, None)
