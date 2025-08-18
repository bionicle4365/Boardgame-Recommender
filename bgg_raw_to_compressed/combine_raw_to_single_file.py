
import sys
from awsglue.transforms import * # type: ignore
from awsglue.utils import getResolvedOptions # type: ignore
from pyspark.context import SparkContext # type: ignore
from awsglue.context import GlueContext # type: ignore
from awsglue.job import Job # type: ignore

# @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ["JOB_NAME"])
sc = SparkContext()
gluc = GlueContext(sc)
spark = gluc.spark_session
job = Job(gluc)
job.init(args["JOB_NAME"], args)

# Script generated for DPU: Glue-2.0
boardgame_app_raw_table = gluc.create_dynamic_frame.from_catalog(
    database="boardgame_app",
    table_name="boardgame_app_raw_table",
    transformation_ctx="boardgame_app_raw_table",
)

s3_location = gluc.write_dynamic_frame.from_options(
    frame=boardgame_app_raw_table, 
    connection_type="s3", 
    format="glueparquet", 
    connection_options={"path": "s3://boardgame-app/data/boardgames_combined/", "partitionKeys": []}, 
    format_options={"compression": "snappy"}, 
    transformation_ctx="s3_location"
)

job.commit()
