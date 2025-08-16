# Use an official Python runtime as a parent image
FROM python:3.12-slim-trixie

# Set the working directory in the container
WORKDIR /app

ENV AWS_REGION=$AWS_REGION

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN echo $AWS_REGION

# Copy the current directory contents into the container at /app
COPY bgg_scraper.py .

# Run the Python script when the container launches
CMD ["python", "bgg_scraper.py"]
