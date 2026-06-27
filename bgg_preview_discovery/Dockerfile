# Use the official Microsoft Playwright Python image (includes browsers)
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script
COPY bgg_preview_discovery.py .

# Run the script
CMD ["python", "bgg_preview_discovery.py"]
