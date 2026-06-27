# Use an official Python runtime as a parent image
FROM amazon/aws-lambda-python:3.12-x86_64

# Install any needed packages specified in requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the current directory contents into the container
COPY bgg_preview_refresh.py ${LAMBDA_TASK_ROOT}

# Run the Python script when the container launches
CMD ["bgg_preview_refresh.lambda_handler"]
