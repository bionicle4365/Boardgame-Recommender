# Boardgame Recommender - Project Roadmap

This document outlines the proposed next steps and architecture enhancements for the Boardgame Recommender project.

---

## Milestone 1: Fix Frontend Security Token Leak (High Priority)

### Objective
Exposing credentials client-side on a public hosting service like GitHub Pages is a significant security risk. We must move the authorization token server-side.

### Tasks
- [x] Locate the hardcoded authorization token in the browser-side script:
  - Reference: [site_ui/collection/index.html:L481](file:///d:/Git/Boardgame-Recommender/site_ui/collection/index.html#L481)
- [x] Remove direct BGG API `fetch()` calls containing `'Authorization': 'Bearer d7c06498-...'` from the frontend files.
- [x] Reroute the frontend request to query a secure backend proxy (API Gateway + Lambda) instead, which inserts the BGG API token from environment variables safely in the cloud.

---

## Milestone 2: Build the Backend Serving AI Layer

### Objective
Establish the bridge between the frontend user interface and the backend AI recommendation engine and database files.

### Tasks
- [ ] **Provision AWS API Gateway**: 
  - Define HTTP/REST API endpoints in the Terraform code (e.g. `/recommendations` and `/collection`).
- [ ] **Request Handler Lambda (AI-Based)**:
  - Build a Lambda function triggered by API Gateway that receives a BGG username.
  - Check the S3 bucket (`s3://boardgame-app/data/users/`) to see if `users/{username}.parquet` already exists.
  - **If not found**: Push the username to the `bgg_user_data_scraper_queue` SQS queue to trigger the scraping Lambda asynchronously. Return a `{"status": "scraping"}` payload to the client.
  - **If found**: Load the user's collection parquet file from S3, extract their liked games, query Amazon Bedrock (e.g., Claude 3 Haiku or Titan) to generate personalized board game recommendations with explanations, and return the recommendations.
- [ ] **Bedrock IAM Permissions**:
  - Grant the serving Lambda IAM permissions to invoke Bedrock models (`bedrock:InvokeModel`).

---

## Milestone 3: Dynamic Frontend Integration

### Objective
Bring the Jekyll website to life by connecting the HTML forms to the newly created backend API.

### Tasks
- [ ] **Recommender Form Logic**:
  - Update [site_ui/recommender/index.html](file:///d:/Git/Boardgame-Recommender/site_ui/recommender/index.html) with custom JavaScript to handle form submission.
- [ ] **Loading & Polling States**:
  - Handle initial scrapers: If the API returns a `{"status": "scraping"}` status, display a loading screen (e.g., *"Scraping your BGG collection for the first time..."*) and poll the API every few seconds until recommendations are ready.
- [ ] **Dynamic Rendering**:
  - Parse the JSON results from the backend and render the recommended games dynamically using HTML elements styled with modern CSS styles (displaying rank, ratings, mechanics, and links to BGG).

---

## Milestone 4: User Data Compaction Job

### Objective
Maintain optimal query performance on Athena as the number of searched users scales.

### Tasks
- [ ] Create a PySpark compaction job (`combine_user_data.py`) for the user data directory:
  - Compiles the thousands of individual `users/{user_id}.parquet` files into a unified dataset under `s3://boardgame-app/data/users_combined/`.
- [ ] Define the Glue resources in [main.tf](file:///d:/Git/Boardgame-Recommender/infrastructure/glue/main.tf):
  - Add the combined user data Glue Catalog table.
  - Wire a Glue Trigger to run this job periodically or as part of the scheduled pipeline workflow.
