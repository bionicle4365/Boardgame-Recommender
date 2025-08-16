# Use an official Python runtime as a parent image
FROM python:3.12-slim-trixie

# Set the working directory in the container
WORKDIR /app

# Set environment variables for the S3 bucket and key
ENV AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
ENV AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY
ENV AWS_REGION="us-east-1"

# Install any needed packages specified in requirements.txt
# Since boto3 and requests are used, we'll install them directly.
# In a real-world scenario, you'd typically have a requirements.txt file.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY bgg_scraper.py .

# Run the Python script when the container launches
CMD ["python", "bgg_scraper.py"]
