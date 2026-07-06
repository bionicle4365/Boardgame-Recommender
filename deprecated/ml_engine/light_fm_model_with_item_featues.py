import pandas as pd
import numpy as np
import pickle
import os
from scipy import sparse
from lightfm import LightFM
from lightfm.data import Dataset
from lightfm.cross_validation import random_train_test_split
from lightfm.evaluation import precision_at_k, recall_at_k, auc_score
from sqlalchemy import create_engine

def create_item_dict(df,id_col,name_col):
    '''
    Creates an item dictionary mapping item_id to item name.
    Arguments: 
        - df = Pandas dataframe containing item information
        - id_col = column name containing unique identifier for an item
        - name_col = column name containing name of the item
    Returns:
        item_dict = Dictionary containing item_id as key and item_name as value
    '''
    return pd.Series(df[name_col].values, index=df[id_col]).to_dict()

def get_user_item_data():
    """
    Function that queries Athena for user-item interaction data. Return it as a dataframe.
    """
    # Using SQLAlchemy to create an engine is the recommended way to connect
    # pandas to databases and avoids the UserWarning.
    # Credentials should be configured in the environment (e.g., IAM role).
    s3_staging_dir = "s3://boardgame-data/test-items/athena-results/"
    region_name = "us-east-1"
    
    # The schema name is part of the query, so it's not needed in the connection string's path.
    conn_str = (
        f"awsathena+rest://@athena.{region_name}.amazonaws.com:443/"
        f"?s3_staging_dir={s3_staging_dir}"
    )
    engine = create_engine(conn_str)

    query = """
    SELECT id, username, avg(rating) as rating FROM boardgame_app.boardgame_app_combined_user_data
    where rating is not null
    group by id, username
    """
    
    df = pd.read_sql(query, engine)
    
    return df

def get_item_data():
    """
    Function that queries Athena for item data. Return it as a dataframe.
    """
    s3_staging_dir = "s3://boardgame-data/test-items/athena-results/"
    region_name = "us-east-1"
    
    conn_str = (
        f"awsathena+rest://@athena.{region_name}.amazonaws.com:443/"
        f"?s3_staging_dir={s3_staging_dir}"
    )
    engine = create_engine(conn_str)
    
    # We only select the columns that are actually used as features or identifiers,
    # avoiding the performance penalty of 'SELECT *'.
    query = """
    SELECT id, name, max_players, rating, categories, mechanics, designers
    FROM boardgame_app.boardgame_app_combined_data
    """
    
    df = pd.read_sql(query, engine)
    
    return df

def item_feature_generator(item_df_source, string_cols, array_cols):
    """Generator function to yield item features for LightFM."""
    for _, row in item_df_source.iterrows():
        features = []
        # Add string features with prefixes
        for col in string_cols:
            if col in row and pd.notna(row[col]):
                val = row[col]
                if col == 'rating':
                    # Ensure rating is treated consistently
                    val = round(float(val), 1)
                features.append(f"{col}:{val}")
        
        # Add array features
        for col in array_cols:
            if col in row and isinstance(row[col], list):
                features.extend(row[col])
        
        yield (row['id'], features)

def load_model_artifacts(output_dir):
    """
    Loads the trained model and associated artifacts from disk.
    
    Args:
        output_dir (str): The directory where artifacts are stored.
        
    Returns:
        tuple: A tuple containing (model, dataset, item_features, item_name_dict).
               Returns (None, None, None, None) if any artifact is missing or corrupt.
    """
    model_path = os.path.join(output_dir, 'best_model.pkl')
    dataset_path = os.path.join(output_dir, 'dataset.pkl')
    item_name_dict_path = os.path.join(output_dir, 'item_name_dict.pkl')
    item_features_path = os.path.join(output_dir, 'item_features.pkl')

    # Check for essential artifacts
    if not all(os.path.exists(p) for p in [model_path, dataset_path, item_name_dict_path]):
        return None, None, None, None

    try:
        print(f"Found pre-trained model artifacts in '{output_dir}/'. Loading them.")
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        with open(dataset_path, 'rb') as f:
            dataset = pickle.load(f)
        with open(item_name_dict_path, 'rb') as f:
            item_name_dict = pickle.load(f)
        
        # Item features are optional, so load them if they exist
        item_features = None
        if os.path.exists(item_features_path):
            with open(item_features_path, 'rb') as f:
                item_features = pickle.load(f)
        
        print("Artifacts loaded successfully.\n")
        return model, dataset, item_features, item_name_dict
    except (pickle.UnpicklingError, EOFError) as e:
        print(f"Error loading artifacts: {e}. Will retrain.")
        return None, None, None, None

def train_and_save_model(training_df, user_rating_df, item_df, output_dir):
    """
    Performs a grid search to train the best LightFM model, evaluates it, and saves the artifacts.
    
    Args:
        training_df (pd.DataFrame): DataFrame with positive user-item interactions for training.
        user_rating_df (pd.DataFrame): DataFrame with all user-item interactions.
        item_df (pd.DataFrame): DataFrame with item metadata/features.
        output_dir (str): Directory to save the trained model and artifacts.
        
    Returns:
        tuple: A tuple of the best artifacts (model, dataset, item_features, item_name_dict).
    """
    print("Starting training process...\n")

    item_name_dict = create_item_dict(item_df, 'id', 'name')

    # Parse array-like string columns into actual lists
    import ast
    all_possible_array_cols = ['categories', 'mechanics', 'designers']
    for col in all_possible_array_cols:
        if col in item_df.columns:
            item_df[col] = item_df[col].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith('[') else x
            )
        else:
            print(f"Warning: Array feature column '{col}' not found in item_df. Skipping.")

    # Feature Engineering: Bin the 'max_players' feature to treat it as a category
    if 'max_players' in item_df.columns:
        bins = [0, 2, 4, 6, np.inf]
        labels = ['1-2 players', '3-4 players', '5-6 players', '7+ players']
        # Convert to string to handle as a categorical feature
        item_df['max_players_binned'] = pd.cut(item_df['max_players'], bins=bins, labels=labels, right=True).astype(str)
        # Replace 'nan' strings that result from NaN inputs, avoiding chained assignment warning.
        item_df['max_players_binned'] = item_df['max_players_binned'].replace('nan', np.nan)
        print("Engineered 'max_players_binned' feature.")

    # 1. Prepare all unique users and items
    all_users = user_rating_df['username'].unique()
    all_items = np.union1d(user_rating_df['id'].unique(), item_df['id'].unique())
    
    # 2. Define feature combinations and hyperparameter grid to test
    feature_sets = [
        {'name': 'No Item Features', 'string_cols': [], 'array_cols': []},
        {'name': 'Categories Only', 'string_cols': [], 'array_cols': ['categories']},
        {'name': 'Mechanics Only', 'string_cols': [], 'array_cols': ['mechanics']},
        {'name': 'Categories & Mechanics', 'string_cols': [], 'array_cols': ['categories', 'mechanics']},
        {'name': 'All Features (excl. Players)', 'string_cols': [], 'array_cols': ['categories', 'mechanics', 'designers']},
    ]

    # Expanded grid to test different loss functions and model capacities.
    param_grid = [
        # A baseline for pure collaborative filtering (works best with 'No Item Features' set)
        {'name': 'WARP - Pure Collaborative', 'loss': 'warp', 'no_components': 60, 'learning_rate': 0.05, 'item_alpha': 1e-5, 'user_alpha': 1e-5},
        # WARP Loss (good for optimizing top of the list)
        {'name': 'WARP - Med Reg', 'loss': 'warp', 'no_components': 75, 'learning_rate': 0.01, 'item_alpha': 1e-1, 'user_alpha': 1e-3},
        {'name': 'WARP - High Reg', 'loss': 'warp', 'no_components': 75, 'learning_rate': 0.01, 'item_alpha': 2e-1, 'user_alpha': 1e-3},
        # BPR Loss (good for overall ranking)
        {'name': 'BPR - Med Reg', 'loss': 'bpr', 'no_components': 75, 'learning_rate': 0.01, 'item_alpha': 1e-1, 'user_alpha': 1e-3},
        # Higher Capacity Model
        {'name': 'WARP - High Capacity', 'loss': 'warp', 'no_components': 100, 'learning_rate': 0.01, 'item_alpha': 1e-1, 'user_alpha': 1e-3},
    ]

    overall_best_config = {'model': None, 'dataset': None, 'item_features': None, 'auc': -1, 'precision': -1, 'params_name': None, 'feature_set_name': None}

    # 3. Loop through feature sets and hyperparameters to find the best model
    for feature_set in feature_sets:
        print(f"\n{'='*20} TESTING FEATURE SET: {feature_set['name']} {'='*20}")
        
        string_feature_cols = feature_set['string_cols']
        array_feature_cols = feature_set['array_cols']

        all_item_features = []
        for col in string_feature_cols:
            if col in item_df.columns:
                # Ensure feature strings are created consistently with the generator.
                if col == 'rating':
                    unique_vals = item_df[col].dropna().astype(float).round(1).unique()
                else:
                    unique_vals = item_df[col].dropna().unique()
                all_item_features.extend([f"{col}:{val}" for val in unique_vals])
        for col in array_feature_cols:
            if col in item_df.columns:
                unique_vals = item_df[col].explode().dropna().unique()
                all_item_features.extend(unique_vals)

        dataset = Dataset()
        use_item_features = bool(all_item_features)
        dataset.fit(users=all_users, items=all_items, item_features=all_item_features if use_item_features else None)

        num_users, num_items = dataset.interactions_shape()
        print(f'Num users: {num_users}, num_items: {num_items}, num_features: {len(all_item_features)}')

        (interactions, weights) = dataset.build_interactions(((x['username'], x['id'], x['weight']) for x in training_df.to_dict(orient='records')))

        item_features = None
        if use_item_features:
            item_features = dataset.build_item_features(item_feature_generator(item_df, string_feature_cols, array_feature_cols))

        (train, test) = random_train_test_split(interactions, test_percentage=0.35, random_state=np.random.RandomState(42))
        (train_weights, _) = random_train_test_split(weights, test_percentage=0.35, random_state=np.random.RandomState(42))

        for params in param_grid:
            model = LightFM(no_components=params['no_components'], learning_rate=params['learning_rate'], loss=params['loss'],
                            item_alpha=params['item_alpha'], user_alpha=params['user_alpha'], random_state=42)

            print(f"\n--- Training Model: {params['name']} ---")
            model.fit(train, sample_weight=train_weights, item_features=item_features, epochs=30, verbose=False, num_threads=8)

            test_auc = auc_score(model, test, train_interactions=train, item_features=item_features, num_threads=8).mean()
            test_precision = precision_at_k(model, test, train_interactions=train, k=10, item_features=item_features, num_threads=8).mean()
            
            print(f'Test AUC Score: {test_auc:.4f} | Test Precision@10: {test_precision:.4f}')

            if test_auc > overall_best_config['auc']:
                print(f"*** New overall best model found! (Optimizing for AUC Score) ***")
                print(f"    Feature Set: '{feature_set['name']}' | Hyperparams: '{params['name']}'")
                print(f"    New Best AUC Score: {test_auc:.4f} | Precision@10: {test_precision:.4f}")
                
                overall_best_config.update({
                    'auc': test_auc, 'precision': test_precision, 'model': model, 'dataset': dataset,
                    'item_features': item_features, 'params_name': params['name'], 'feature_set_name': feature_set['name']
                })

    print("\n=============================================")
    print("Finished grid search. Optimization Goal: Highest AUC Score")
    print(f"The best performing model was '{overall_best_config['params_name']}' with feature set '{overall_best_config['feature_set_name']}'")
    print(f"achieving a Test AUC score of: {overall_best_config['auc']:.4f} and a Precision@10 of: {overall_best_config['precision']:.4f}")
    print("=============================================\n")

    best_model = overall_best_config['model']
    best_dataset = overall_best_config['dataset']
    best_item_features = overall_best_config['item_features']

    if best_model and best_dataset:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Saving model artifacts to '{output_dir}/'...")

        with open(os.path.join(output_dir, 'best_model.pkl'), 'wb') as f: pickle.dump(best_model, f)
        with open(os.path.join(output_dir, 'dataset.pkl'), 'wb') as f: pickle.dump(best_dataset, f)
        with open(os.path.join(output_dir, 'item_name_dict.pkl'), 'wb') as f: pickle.dump(item_name_dict, f)

        if best_item_features is not None:
            with open(os.path.join(output_dir, 'item_features.pkl'), 'wb') as f: pickle.dump(best_item_features, f)
        
        print("Artifacts saved successfully.\n")
        return best_model, best_dataset, best_item_features, item_name_dict
    
    return None, None, None, None

def generate_recommendations(model, dataset, item_features, item_name_dict, usernames, user_rating_df):
    """
    Generates and prints top-k recommendations for a list of users.
    
    Args:
        model (LightFM): The trained LightFM model.
        dataset (Dataset): The LightFM dataset object.
        item_features (sparse matrix): The item features matrix.
        item_name_dict (dict): Dictionary mapping item IDs to names.
        usernames (list): A list of usernames to generate recommendations for.
        user_rating_df (pd.DataFrame): DataFrame with all user-item interactions, used for filtering.
    """
    user_id_map, _, item_id_map, _ = dataset.mapping()
    
    for username in usernames:
        if username in user_id_map:
            user_id = user_id_map[username]
            
            _, num_items = dataset.interactions_shape()
            
            # Get items the user has already rated to filter them out from recommendations
            known_item_ids = set(user_rating_df[user_rating_df.username == username]['id'])
            
            scores = model.predict(user_id, np.arange(num_items), item_features=item_features, num_threads=8)
            
            top_items_indices = np.argsort(-scores)

            inv_item_map = {v: k for k, v in item_id_map.items()}
            
            recommendations = []
            for item_index in top_items_indices:
                if len(recommendations) >= 10:
                    break
                
                original_item_id = inv_item_map[item_index]
                # Add to recommendations only if the user hasn't rated it yet
                if original_item_id not in known_item_ids:
                    item_name = item_name_dict.get(original_item_id, f"Unknown ID: {original_item_id}")
                    recommendations.append(item_name)
            print(f"Top 10 recommendations for {username}:")
            for item_name in recommendations:
                print(f"  - {item_name}")
            print()
        else:
            print(f"User '{username}' not in the training data.\n")

if __name__ == "__main__":
    # 1. Load and prepare user interaction data
    user_rating_df = get_user_item_data()
    user_rating_df['rating'] = pd.to_numeric(user_rating_df['rating'], errors='coerce')
    user_rating_df.dropna(subset=['username', 'id', 'rating'], inplace=True)

    positive_interaction_threshold = 8.0
    training_df = user_rating_df[user_rating_df['rating'] >= positive_interaction_threshold].copy()    
    training_df['weight'] = (training_df['rating'] - positive_interaction_threshold) + 1.0

    print(f"Total interactions loaded: {len(user_rating_df)}")
    print(f"Using {len(training_df)} interactions for training (rating >= {positive_interaction_threshold}).\n")

    output_dir = 'model_artifacts'
    # 2. Try to load existing model artifacts
    artifacts = load_model_artifacts(output_dir)
    best_model, best_dataset, best_item_features, item_name_dict = artifacts

    # 3. If loading fails, train a new model
    if not best_model or not best_dataset:
        item_df = get_item_data()
        artifacts = train_and_save_model(
            training_df, user_rating_df, item_df, output_dir
        )
        best_model, best_dataset, best_item_features, item_name_dict = artifacts

    # 4. Generate recommendations if a model is available
    if best_model and best_dataset:
        usernames_to_recommend = ['bionicle4365', 'janeivy11']
        print("--- Generating Recommendations ---")
        generate_recommendations(
            model=best_model,
            dataset=best_dataset,
            item_features=best_item_features,
            item_name_dict=item_name_dict,
            usernames=usernames_to_recommend,
            user_rating_df=user_rating_df
        )
    else:
        print("No model was successfully trained or loaded. Exiting.")
