# Use official AWS Lambda Python runtime as a parent image
FROM amazon/aws-lambda-python:3.12-x86_64

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install packages
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy script handler
COPY bgg_taste_analytics.py ${LAMBDA_TASK_ROOT}

# Set lambda handler
CMD ["bgg_taste_analytics.lambda_handler"]
