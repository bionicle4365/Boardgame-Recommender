# Use an official Python runtime as a parent image
FROM amazon/aws-lambda-python:3.12-x86_64

# Install any needed packages specified in requirements.txt
# Since boto3 and requests are used, we'll install them directly.
# In a real-world scenario, you'd typically have a requirements.txt file.
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the current directory contents into the container at /app
COPY user_data_scraper.py ${LAMBDA_TASK_ROOT}

# Run the Python script when the container launches
CMD ["user_data_scraper.lambda_handler"]
