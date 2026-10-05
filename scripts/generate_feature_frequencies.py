"""
Catalog Feature Frequencies Generator for Milestone 62.

Calculates category and mechanic document frequencies across the BGG catalog parquet
and generates `catalog_feature_frequencies.json` with precomputed IDF factors:
    IDF(feature) = ln(1.0 + N_catalog / N_feature)
"""
import argparse
import json
import math
import os
import shutil
from datetime import datetime, timezone
import numpy as np
import pandas as pd


def generate_catalog_feature_frequencies(catalog_df, output_path=None):
    """
    Computes catalog document frequencies and IDF factors for mechanics and categories.
    
    Args:
        catalog_df: pandas DataFrame or PyArrow Table containing catalog data.
        output_path: Optional path to write catalog_feature_frequencies.json.
        
    Returns:
        dict: The frequencies and IDF factors dictionary.
    """
    if hasattr(catalog_df, 'select') and hasattr(catalog_df, 'to_pandas'):
        cols = [c for c in ['mechanics', 'categories'] if c in catalog_df.column_names]
        df = catalog_df.select(cols).to_pandas()
        total_games = catalog_df.num_rows
    else:
        df = catalog_df
        total_games = len(df)

    mechanic_counts = {}
    category_counts = {}

    if 'mechanics' in df.columns:
        for val in df['mechanics'].dropna():
            if isinstance(val, (list, np.ndarray, tuple, set)):
                unique_mechs = set(val)
            elif isinstance(val, str):
                unique_mechs = {m.strip() for m in val.split(',') if m.strip()}
            else:
                continue
            for m in unique_mechs:
                mechanic_counts[m] = mechanic_counts.get(m, 0) + 1

    if 'categories' in df.columns:
        for val in df['categories'].dropna():
            if isinstance(val, (list, np.ndarray, tuple, set)):
                unique_cats = set(val)
            elif isinstance(val, str):
                unique_cats = {c.strip() for c in val.split(',') if c.strip()}
            else:
                continue
            for c in unique_cats:
                category_counts[c] = category_counts.get(c, 0) + 1

    # Sort descending by count
    sorted_mechs = dict(sorted(mechanic_counts.items(), key=lambda x: x[1], reverse=True))
    sorted_cats = dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True))

    mechanic_idf = {
        m: round(math.log(1.0 + total_games / count), 4)
        for m, count in sorted_mechs.items()
    } if total_games > 0 else {}

    category_idf = {
        c: round(math.log(1.0 + total_games / count), 4)
        for c, count in sorted_cats.items()
    } if total_games > 0 else {}

    result = {
        "total_games": int(total_games),
        "mechanics": sorted_mechs,
        "categories": sorted_cats,
        "mechanic_idf": mechanic_idf,
        "category_idf": category_idf,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(description="Generate catalog feature frequencies and IDF weights.")
    parser.add_argument("--catalog", default="scratch/catalog.parquet", help="Path to catalog parquet file")
    parser.add_argument("--output", default="data/catalog_feature_frequencies.json", help="Path to write JSON output")
    parser.add_argument("--bundle", action="store_true", default=False, help="Also copy to bgg_recommender and bgg_taste_analytics")
    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    catalog_path = os.path.join(repo_root, args.catalog) if not os.path.isabs(args.catalog) else args.catalog
    output_path = os.path.join(repo_root, args.output) if not os.path.isabs(args.output) else args.output

    if not os.path.exists(catalog_path):
        raise FileNotFoundError(f"Catalog parquet not found at: {catalog_path}")

    print(f"Reading catalog from {catalog_path}...")
    df = pd.read_parquet(catalog_path)
    print(f"Loaded {len(df)} games from catalog.")

    print("Calculating mechanic and category document frequencies...")
    result = generate_catalog_feature_frequencies(df, output_path=output_path)
    print(f"Generated frequencies for {len(result['mechanics'])} mechanics and {len(result['categories'])} categories.")
    print(f"Saved primary asset to: {output_path}")

    if args.bundle:
        bundle_targets = [
            os.path.join(repo_root, "bgg_taste_analytics", "catalog_feature_frequencies.json"),
            os.path.join(repo_root, "bgg_recommender", "catalog_feature_frequencies.json")
        ]
        for target in bundle_targets:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(output_path, target)
            print(f"Bundled copy saved to: {target}")


if __name__ == "__main__":
    main()
