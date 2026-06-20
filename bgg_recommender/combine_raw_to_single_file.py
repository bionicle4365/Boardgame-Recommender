import os
import pyarrow.dataset as ds
import pyarrow.fs as fs
import pyarrow.parquet as pq

def lambda_handler(event, context):
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    raw_prefix = os.environ.get('RAW_PREFIX', 'data/boardgames/')
    combined_prefix = os.environ.get('COMBINED_PREFIX', 'data/boardgames_combined/')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    
    print(f"Starting serverless S3 Parquet compaction...")
    print(f"Source prefix: s3://{bucket_name}/{raw_prefix}")
    print(f"Target location: s3://{bucket_name}/{combined_prefix}catalog.parquet")
    
    try:
        # Initialize PyArrow S3 filesystem
        s3_fs = fs.S3FileSystem(region=aws_region)
        
        # Read all parquet files under the raw prefix in S3 directly using PyArrow Dataset API
        source_path = f"{bucket_name}/{raw_prefix}"
        print(f"Reading all raw Parquet files from {source_path}...")
        dataset = ds.dataset(source_path, format="parquet", filesystem=s3_fs)
        
        # Convert dataset to a PyArrow Table (in-memory merge)
        print("Converting dataset to PyArrow Table...")
        table = dataset.to_table()
        print(f"Merge complete. Combined table has {table.num_rows} records and {table.num_columns} columns.")
        
        # Define output path
        output_file_path = f"{bucket_name}/{combined_prefix}catalog.parquet"
        print(f"Writing Snappy-compressed combined Parquet file to s3://{output_file_path}...")
        
        # Write back to S3 as a single snappy-compressed Parquet file
        pq.write_table(table, output_file_path, filesystem=s3_fs, compression="snappy")
        print("S3 Parquet compaction completed successfully!")
        
        return {
            'statusCode': 200,
            'body': f"Successfully compacted {table.num_rows} records into catalog.parquet"
        }
        
    except Exception as e:
        print(f"CRITICAL ERROR during compaction: {e}")
        return {
            'statusCode': 500,
            'body': f"Compaction failed: {str(e)}"
        }

if __name__ == '__main__':
    # Local debugging
    os.environ['S3_BUCKET_NAME'] = 'boardgame-app'
    lambda_handler({}, None)
