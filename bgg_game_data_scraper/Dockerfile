# Use an official Python runtime as a parent image
FROM amazon/aws-lambda-python:3.11-x86_64

# Set environment variables for the S3 bucket and key
ENV AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
ENV AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY
ENV S3_BUCKET_NAME=$S3_BUCKET_NAME

# Install any needed packages specified in requirements.txt
# Since boto3 and requests are used, we'll install them directly.
# In a real-world scenario, you'd typically have a requirements.txt file.
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the current directory contents into the container at /app
COPY bgg_game_data.py ${LAMBDA_TASK_ROOT}

# Run the Python script when the container launches
CMD ["bgg_game_data.lambda_handler"]
