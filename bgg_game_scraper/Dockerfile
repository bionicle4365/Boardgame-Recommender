# Use an official Python runtime as a parent image
FROM python:3.12-slim-trixie

# Set the working directory in the container
WORKDIR /app

# Install any needed packages specified in requirements.txt
# Since boto3 and requests are used, we'll install them directly.
# In a real-world scenario, you'd typically have a requirements.txt file.
ARG AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
ARG AWS_REGION=$AWS_REGION
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install awscli
RUN aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID"
RUN aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY"
RUN aws configure set region "$AWS_REGION"

# Copy the current directory contents into the container at /app
COPY bgg_scraper.py .

# Run the Python script when the container launches
CMD ["python", "bgg_scraper.py"]
