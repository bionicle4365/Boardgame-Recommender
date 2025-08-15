import boto3
import requests
import xml.etree.ElementTree as ET
import os
import sys # Import sys for exiting on critical errors

def main():
    """
    Main function to scrape BoardGameGeek API.
    Reads a starting ID from S3, queries BGG API, and checks if it's a boardgame.
    """
    s3_bucket_name = os.environ.get('S3_BUCKET_NAME', 'your-s3-bucket-name') # Replace with your S3 bucket name
    s3_key = os.environ.get('S3_KEY', 'bgg-scraper/bgg_start_id.txt') # Replace with your S3 key for the ID file
    bgg_api_base_url = "https://boardgamegeek.com/xmlapi2/thing"

    s3 = boto3.client('s3')
    start_id = None

    try:
        # 1. Read starting ID from S3
        print(f"Attempting to read ID from s3://{s3_bucket_name}/{s3_key}")
        response = s3.get_object(Bucket=s3_bucket_name, Key=s3_key)
        start_id_str = response['Body'].read().decode('utf-8').strip()
        start_id = int(start_id_str)
        print(f"Successfully read starting ID: {start_id}")

    except s3.exceptions.NoSuchKey:
        print(f"Error: S3 key '{s3_key}' not found in bucket '{s3_bucket_name}'. Exiting.")
        sys.exit(1) # Exit with an error code
    except Exception as e:
        print(f"Error reading from S3: {e}. Exiting.")
        sys.exit(1) # Exit with an error code

    if start_id is None:
        print("Failed to retrieve a valid starting ID. Exiting.")
        sys.exit(1) # Exit with an error code

    # 2. Query BoardGameGeek API
    api_url = f"{bgg_api_base_url}?id={start_id}"
    print(f"Querying BGG API: {api_url}")

    try:
        response = requests.get(api_url)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        xml_data = response.content
        print("Successfully received response from BGG API.")

        # 3. Parse XML response
        root = ET.fromstring(xml_data)

        # 4. Check if item exists and is of type 'boardgame'
        item = root.find('item')
        if item is not None:
            item_id = item.get('id')
            item_type = item.get('type')
            item_name_element = item.find("./name[@type='primary']")
            item_name = item_name_element.get('value') if item_name_element is not None else "N/A"

            print(f"Found item ID: {item_id}, Type: {item_type}, Name: {item_name}")

            if item_type == 'boardgame':
                result_message = f"ID {start_id} is a boardgame: {item_name}"
                print(result_message)
            else:
                result_message = f"ID {start_id} exists but is not a boardgame (Type: {item_type}). Name: {item_name}"
                print(result_message)
        else:
            result_message = f"ID {start_id} does not exist or is not found in BGG API response."
            print(result_message)

    except requests.exceptions.RequestException as e:
        print(f"Error querying BGG API: {e}. Exiting.")
        sys.exit(1) # Exit with an error code
    except ET.ParseError as e:
        print(f"Error parsing XML from BGG API: {e}. Exiting.")
        sys.exit(1) # Exit with an error code
    except Exception as e:
        print(f"An unexpected error occurred: {e}. Exiting.")
        sys.exit(1) # Exit with an error code

if __name__ == '__main__':
    # When running in an ECR container, this script will be executed directly.
    # Environment variables for S3_BUCKET_NAME and S3_KEY should be set in the container definition.
    main()
