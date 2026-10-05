# BGG Taste Analytics Lambda

An asynchronous analytics worker Lambda that processes a user's BGG ratings and collection data to generate a multi-dimensional, TF-IDF discounted **Player Taste Profile**.

---

## Architecture Overview

```mermaid
graph LR
    UserScraper[BGG User Scraper] -->|Collection Parquet Created| S3User[(S3: data/users/{username}.parquet)]
    UserScraper -->|Async SQS Trigger| TasteLambda[BGG Taste Analytics Lambda]
    
    Catalog[(S3: catalog.parquet)] --> TasteLambda
    IDFCache[(S3: catalog_feature_frequencies.json)] --> TasteLambda
    
    subgraph Analytics Pipeline
        TasteLambda --> LogDamping[Logarithmic Frequency Damping]
        LogDamping --> IDFScaling[Catalog IDF Discounting]
        IDFScaling --> MeanComp[Rating-Weighted Mean Complexity]
    end
    
    MeanComp --> S3Profile[(S3: data/users/{username}_taste_profile.json)]
```

---

## Algorithm Details

### 1. Rating-Weighted Affinity with Logarithmic Damping
Raw tag frequency can skew heavily if a player owns dozens of small expansions with the same mechanic. The taste engine applies logarithmic damping to count frequencies:
$$\text{TF}(t, u) = \ln(1 + \text{count}(t)) \times (\text{user\_rating} - \text{baseline})$$
Where liked games ($\ge 7.0$) contribute positive affinity and disliked games contribute negative weight.

### 2. Catalog-Wide IDF (Inverse Document Frequency) Discounting
Ubiquitous tags (such as *"Card Game"*, *"Hand Management"*, or *"Dice Rolling"*) appear in over 40% of all published games. To ensure recommendations elevate a player's distinctive preferences rather than generic baseline tags, the engine applies smoothed catalog IDF scaling:
$$\text{IDF}(t) = \ln\left(1 + \frac{N_{\text{catalog}}}{N_t}\right)$$
$$\text{Affinity}(t) = \text{TF}(t, u) \times \text{IDF}(t)$$
This elevates distinctive mechanics like *"Trick-taking"*, *"Deck Construction"*, or *"Worker Placement"* over generic categories.

### 3. Rating-Weighted Mean Complexity
Rather than categorizing players into rigid weight buckets ("Casual" vs "Heavy"), the engine calculates a continuous rating-weighted mean complexity:
$$\mu_{\text{comp}} = \frac{\sum_{g \in \text{liked}} \text{rating}(g) \times \text{complexity}(g)}{\sum_{g \in \text{liked}} \text{rating}(g)}$$

---

## Taste Profile Schema (`data/users/{username}_taste_profile.json`)

```json
{
  "mech_weights": {
    "Trick-taking": 14.52,
    "Hand Management": 6.84,
    "Worker Placement": 5.21
  },
  "cat_weights": {
    "Economic": 8.75,
    "Card Game": 4.12
  },
  "raw_mech_weights": {
    "Trick-taking": 3.76,
    "Hand Management": 4.88
  },
  "raw_cat_weights": {
    "Economic": 3.42,
    "Card Game": 4.15
  },
  "complexity_weights": {
    "Light": 0.0,
    "Medium-Light": 2.5,
    "Medium-Heavy": 4.0,
    "Heavy": 1.0
  },
  "user_mean_complexity": 2.85,
  "designer_weights": {
    "Uwe Rosenberg": 4.2
  },
  "publisher_weights": {
    "Lookout Games": 4.2
  },
  "idf_applied": true,
  "generated_at": "2026-10-05T13:20:00.000000+00:00"
}
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `S3_OUTPUT_BUCKET_NAME` | Data lake bucket name | `boardgame-app` |
| `LOG_LEVEL` | Logging level | `INFO` |

---

## Local Development & Testing

Run taste analytics unit tests:
```bash
pytest tests/test_bgg_taste_analytics.py -v
```
