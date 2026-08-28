# Local Development Guide

This guide walks you through setting up and running the **Boardgame Recommender** frontend locally.

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Zero-Config Quick Start (Mock API Mode)](#2-zero-config-quick-start-mock-api-mode)
3. [Connecting to Real Backend Services](#3-connecting-to-real-backend-services)
   - [Approach A: Direct Jekyll Multi-Config Override (Recommended)](#approach-a-direct-jekyll-multi-config-override-recommended)
   - [Approach B: `.env.local` + Config Generator Script](#approach-b-envlocal--config-generator-script)
4. [Running the Local Jekyll Server](#4-running-the-local-jekyll-server)
5. [Testing & Verification](#5-testing--verification)
6. [Troubleshooting & FAQs](#6-troubleshooting--faqs)

---

## 1. Prerequisites

Ensure you have the following installed on your machine:
* **Ruby** (v3.0+) and **Bundler**
* **Python** (v3.10+)
* **Node.js** (v18+)

### Install Jekyll Dependencies
From the repository root, install the required Ruby gems:
```bash
cd site_ui
bundle install
```

---

## 2. Zero-Config Quick Start (Mock API Mode)

The site includes built-in mock responses for offline development without needing any AWS credentials or active internet connection to backend Lambdas.

Simply run:
```bash
cd site_ui
bundle exec jekyll serve
```
Open [http://localhost:4000/Boardgame-Recommender/](http://localhost:4000/Boardgame-Recommender/) in your browser:
* Collection searches will query the public BGG XMLAPI2 directly.
* Recommendation, Profile, Groups, and Conventions requests will be served by the client mock engine in `utils.js`.

---

## 3. Connecting to Real Backend Services

When you want to test against live AWS Lambda APIs, DynamoDB preferences, and Cognito User Pools, you can supply your real credentials using either of the following approaches. **Both methods use gitignored files so your credentials will never be committed to git.**

### Approach A: Direct Jekyll Multi-Config Override (Recommended)

1. Copy the example configuration file:
   ```bash
   cp site_ui/_config.local.yml.example site_ui/_config.local.yml
   ```
2. Open `site_ui/_config.local.yml` and replace the placeholder values with your real AWS endpoints:
   ```yaml
   baseurl: ""
   url: "http://localhost:4000"
   api_url: "https://your-api-id.execute-api.us-east-1.amazonaws.com"
   cognito_region: "us-east-1"
   cognito_client_id: "your_cognito_app_client_id"
   cognito_user_pool_id: "us-east-1_your_pool_id"
   ```
3. Run Jekyll using multi-config mode (see [Section 4](#4-running-the-local-jekyll-server)).

---

### Approach B: `.env.local` + Config Generator Script

If you prefer using standard environment variable files:

1. Copy the example environment file:
   ```bash
   cp site_ui/.env.local.example site_ui/.env.local
   ```
2. Edit `site_ui/.env.local` with your values:
   ```env
   API_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com
   COGNITO_REGION=us-east-1
   COGNITO_CLIENT_ID=your_cognito_app_client_id
   COGNITO_USER_POOL_ID=us-east-1_your_pool_id
   BASEURL=
   URL=http://localhost:4000
   ```
3. Run the generator script to compile your `.env.local` into `site_ui/_config.local.yml`:
   ```bash
   python scripts/gen_local_config.py
   ```

---

## 4. Running the Local Jekyll Server

To launch the local development server with your configuration override applied:

```bash
cd site_ui
bundle exec jekyll serve --config _config.yml,_config.local.yml --livereload
```

* **Live Reload:** Changes to HTML, CSS, or JS files will automatically refresh your browser.
* **URL:** Navigate to [http://localhost:4000](http://localhost:4000) (if `baseurl` was set to `""`) or [http://localhost:4000/Boardgame-Recommender/](http://localhost:4000/Boardgame-Recommender/).

---

## 5. Testing & Verification

### Running Automated Backend & Frontend Tests
To verify all Python Lambda tests and frontend tests pass:

```bash
# Run backend pytest suite
python -m pytest

# Run frontend Vitest suite (from site_ui directory)
cd site_ui
npm test
```

---

## 6. Troubleshooting & FAQs

### Q: Why do API requests fail with CORS errors locally?
* Verify that `http://localhost:4000` is listed in your API Gateway's allowed CORS origins in `infrastructure/variables.tf`.

### Q: Why does Cognito login redirect to a blank page or error?
* Ensure `http://localhost:4000` is registered as a valid Callback/Redirect URL in your Cognito User Pool Client settings if you are using hosted UI login.

### Q: How do I switch back to Mock API mode?
* Simply start Jekyll without the `_config.local.yml` flag:
  ```bash
  bundle exec jekyll serve
  ```
