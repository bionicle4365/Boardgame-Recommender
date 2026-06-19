import sys
from awsglue.transforms import * # type: ignore
from awsglue.utils import getResolvedOptions # type: ignore
from pyspark.context import SparkContext # type: ignore
from awsglue.context import GlueContext # type: ignore
from awsglue.job import Job # type: ignore
from awsglue.dynamicframe import DynamicFrame # type: ignore
import boto3

# @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
gluc = GlueContext(sc)
spark = gluc.spark_session
# Disable vectorized reader to handle physical type discrepancies in parquet (e.g., empty lists defaulting to INT32)
spark.conf.set("spark.sql.parquet.enableVectorizedReader", "false")
job = Job(gluc)
job.init(args["JOB_NAME"], args)

boardgame_app_raw_table = gluc.create_dynamic_frame.from_catalog(
    database="boardgame_app",
    table_name="boardgame_app_raw_table",
    transformation_ctx="boardgame_app_raw_table",
)

# Coalesce dynamic frame to 1 partition by converting to Spark DataFrame and back
coalesced_df = boardgame_app_raw_table.toDF().coalesce(1)
boardgame_app_combined = DynamicFrame.fromDF(coalesced_df, gluc, "boardgame_app_combined")

purge_s3 = gluc.purge_s3_path(
    s3_path="s3://boardgame-app/data/boardgames_combined/",
    options={"retentionPeriod": 0}
)

s3_location = gluc.write_dynamic_frame.from_options(
    frame=boardgame_app_combined, 
    connection_type="s3", 
    format="glueparquet", 
    connection_options={"path": "s3://boardgame-app/data/boardgames_combined/", "partitionKeys": []}, 
    format_options={"compression": "snappy"}, 
    transformation_ctx="s3_location"
)

# Post-write cleanup to rename the single dynamic partition file to a predictable name: catalog.parquet
s3_path = "s3://boardgame-app/data/boardgames_combined/"
path_parts = s3_path.replace("s3://", "").split("/")
bucket_name = path_parts[0]
prefix = "/".join(path_parts[1:])

s3_client = boto3.client('s3')
response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
parquet_key = None
keys_to_delete = []

if 'Contents' in response:
    for obj in response['Contents']:
        key = obj['Key']
        if key.endswith('.parquet') and not key.endswith('catalog.parquet'):
            parquet_key = key
        if key != prefix:  # Avoid deleting the folder directory prefix itself
            keys_to_delete.append({'Key': key})

if parquet_key:
    target_key = prefix + "catalog.parquet"
    print(f"Renaming/Copying {parquet_key} to {target_key}")
    s3_client.copy_object(
        Bucket=bucket_name,
        Key=target_key,
        CopySource={'Bucket': bucket_name, 'Key': parquet_key}
    )
    
    # Filter keys_to_delete to NOT delete the newly created catalog.parquet
    keys_to_delete = [k for k in keys_to_delete if k['Key'] != target_key]
    if keys_to_delete:
        print(f"Cleaning up temporary files: {keys_to_delete}")
        s3_client.delete_objects(Bucket=bucket_name, Delete={'Objects': keys_to_delete})

job.commit()
