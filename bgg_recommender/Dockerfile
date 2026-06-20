# Use official AWS Lambda Python runtime as a parent image
FROM amazon/aws-lambda-python:3.12-x86_64

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install packages
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy script handlers
COPY bgg_recommender.py combine_raw_to_single_file.py ${LAMBDA_TASK_ROOT}

# Set lambda handler
CMD ["bgg_recommender.lambda_handler"]
