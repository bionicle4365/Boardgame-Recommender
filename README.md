# Boardgame Recommender

[![BGG Game Scraper Docker Image](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/scraper-docker-image.yml/badge.svg)](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/scraper-docker-image.yml) [![BGG Game Data Scraper Docker Image](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/data-scraper-docker-image.yml/badge.svg)](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/data-scraper-docker-image.yml) [![BGG User Data Scraper Docker Image](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/user-scraper-docker-image.yml/badge.svg)](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/user-scraper-docker-image.yml) [![ECR Terraform](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/ecr_terraform.yml/badge.svg)](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/ecr_terraform.yml) [![Terraform](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/terraform.yml/badge.svg)](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/terraform.yml) [![Deploy Jekyll with GitHub Pages](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/jekyll-gh-pages.yml/badge.svg)](https://github.com/bionicle4365/Boardgame-Recommender/actions/workflows/jekyll-gh-pages.yml)

An end-to-end cloud-native serverless system that scrapes board game catalogs and player collection data from the BoardGameGeek (BGG) API, aggregates it into an optimized S3 data lake, and generates personalized board game recommendations with AI-driven explanations.

---

## System Architecture

```mermaid
graph TD
    Client[Jekyll Website UI] -->|1. Register / Login| Cognito[Amazon Cognito User Pool]
    Client -->|2. Query recommendations| APIGW[AWS API Gateway]
    Client -->|3. Sync preferences & groups| APIGW
    Client -->|4. Bypass CORS BGG fetch| APIGW
    
    APIGW -->|Route: /recommendations| ServingLambda[BGG Recommender Lambda]
    APIGW -->|Route: /preferences (JWT Secure)| PreferencesLambda[BGG Preferences Lambda]
    APIGW -->|Route: /collection| ProxyLambda[BGG API Proxy Lambda]
    
    PreferencesLambda -->|Read/Write| DynamoDB[(DynamoDB User Preferences)]
    
    ServingLambda -->|Check if profile scraped| S3Users[(S3 User Profiles)]
    
    %% Scraper triggers
    ServingLambda -->|Profile not found: Queue scrape| SQSUser[SQS User Queue]
    SQSUser -->|Trigger| UserScraper[BGG User Scraper Lambda]
    UserScraper -->|Scrape collection Parquet| S3Users
    
    %% Game Scraper Pipeline
    ECS[ECS Fargate Scraper] -->|Continuous game IDs| SQSGame[SQS Game Queue]
    SQSGame -->|Trigger| GameDataScraper[BGG Game Data Scraper Lambda]
    GameDataScraper -->|Write raw details| S3Raw[(S3 Raw Catalog)]
    
    %% Compaction
    EventBridge[EventBridge Weekly Trigger] -->|Trigger| CompactorLambda[BGG Compactor Lambda]
    S3Raw -->|Download raw Parquets| CompactorLambda
    CompactorLambda -->|Compact Snappy Parquet| S3Combined[(S3 Combined Catalog)]
    
    %% Recommendation retrieval
    S3Combined -->|Download catalog.parquet| ServingLambda
    S3Users -->|Download user Parquet| ServingLambda
    ServingLambda -->|Jaccard Similarity Match| Candidates[Top Candidates]
    Candidates -->|Prompt| Bedrock[Amazon Bedrock Nova Micro]
    Bedrock -->|Personalized JSON| ServingLambda
    ServingLambda -->|JSON recommendations| Client
```

---

## Directory Structure

* **[site_ui/](file:///d:/Git/Boardgame-Recommender/site_ui)**: The frontend Jekyll dashboard, collection browser, and recommendation interface hosted on GitHub Pages.
* **[bgg_recommender/](file:///d:/Git/Boardgame-Recommender/bgg_recommender)**: Python container-based Lambda served via API Gateway. Extracts catalog & user collections from S3, executes Jaccard matching, and uses Bedrock Amazon Nova Micro for reasoning. Also contains the entry point for the weekly compactor Lambda (`combine_raw_to_single_file.py`).
* **[bgg_preferences/](file:///d:/Git/Boardgame-Recommender/bgg_preferences)**: Python Lambda function that handles storage and synchronization of user preferences, playgroups, and weights in Amazon DynamoDB, secured by Cognito JWT validation.
* **[bgg_api_proxy/](file:///d:/Git/Boardgame-Recommender/bgg_api_proxy)**: Proxy Lambda function that forwards requests to the BGG XML API v2 collection endpoint to bypass frontend CORS restrictions.
* **[bgg_game_scraper/](file:///d:/Git/Boardgame-Recommender/bgg_game_scraper)**: Continuous containerized python scraper (run in ECS Fargate) that discovers boardgame IDs and pushes them to SQS.
* **[bgg_game_data_scraper/](file:///d:/Git/Boardgame-Recommender/bgg_game_data_scraper)**: SQS-triggered Lambda scraper that downloads game details (mechanics, complexity, name, year) and writes them to raw S3 Parquet.
* **[bgg_user_data_scraper/](file:///d:/Git/Boardgame-Recommender/bgg_user_data_scraper)**: SQS-triggered Lambda scraper that downloads a BGG user's collection, rated games, and ownership status.
* **[bgg_raw_to_compressed/](file:///d:/Git/Boardgame-Recommender/bgg_raw_to_compressed)**: *(Deprecated)* Old AWS Glue PySpark ETL scripts, now replaced by the serverless python compactor Lambda located under `bgg_recommender/`.
* **[infrastructure/](file:///d:/Git/Boardgame-Recommender/infrastructure)**: Core Terraform templates provisioning S3, DynamoDB, Cognito User Pools, API Gateway integrations, Lambda functions, and EventBridge schedules.
* **[ecr_infrastructure/](file:///d:/Git/Boardgame-Recommender/ecr_infrastructure)**: Terraform templates configuring ECR repositories and repository lifecycle rules.
* **[ml_engine/](file:///d:/Git/Boardgame-Recommender/ml_engine)**: Experimental LightFM collaborative filtering training script using PyAthena connection logic.

---

## GitHub Actions Workflows

All Docker containers and Terraform infrastructures are continuously deployed via GitHub Actions:
* **`jekyll-gh-pages.yml`**: Builds and deploys Jekyll website frontend to GitHub Pages.
* **`recommender-docker-image.yml`**: Builds and pushes `bgg_recommender` Lambda container image to Amazon ECR.
* **`scraper-docker-image.yml`**: Builds and pushes `bgg_game_scraper` ECS container image to Amazon ECR.
* **`data-scraper-docker-image.yml`**: Builds and pushes `bgg_game_data_scraper` Lambda container image to Amazon ECR.
* **`user-scraper-docker-image.yml`**: Builds and pushes `bgg_user_data_scraper` Lambda container image to Amazon ECR.
* **`terraform.yml`**: Continuous integration plan/apply execution for core infrastructure.
* **`ecr_terraform.yml`**: Plan/apply execution for ECR container repositories.
