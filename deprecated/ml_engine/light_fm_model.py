import pandas as pd
import numpy as np
from scipy import sparse
from lightfm import LightFM
from lightfm.data import Dataset
from lightfm.evaluation import precision_at_k, auc_score
from pyathena import connect

def create_interaction_matrix(df,user_col, item_col, rating_col, norm= False, threshold = None):
    '''
    Creates an interaction matrix DataFrame
    Arguments:
        df = Pandas DataFrame containing user-item interactions
        user_col = column name containing user's identifier
        item_col = column name containing item's identifier
        rating col = column name containing user rating on given item
        norm (optional) = True if a normalization of ratings is needed
        threshold (required if norm = True) = value above which the rating is favorable
    Returns:
        Pandas DataFrame with user-item interactions
    '''
    interactions = df.groupby([user_col, item_col])[rating_col] \
            .sum().unstack().reset_index(). \
            fillna(0).set_index(user_col)
    if norm:
        interactions = interactions.applymap(lambda x: 1 if x > threshold else 0)
    return interactions

def create_user_dict(interactions):
    '''
    Creates a user dictionary based on their index and number in interaction dataset
    Arguments:
        interactions - DataFrame with user-item interactions
    Returns:
        user_dict - Dictionary containing interaction_index as key and user_id as value
    '''
    user_id = list(interactions.index)
    user_dict = {}
    counter = 0 
    for i in user_id:
        user_dict[i] = counter
        counter += 1
    return user_dict

def create_item_dict(df,id_col,name_col):
    '''
    Creates an item dictionary based on their item_id and item name
    Arguments: 
        - df = Pandas dataframe containing item information
        - id_col = column name containing unique identifier for an item
        - name_col = column name containing name of the item
    Returns:
        item_dict = Dictionary containing item_id as key and item_name as value
    '''
    item_dict ={}
    for i in range(df.shape[0]):
        item_dict[(df.loc[i,id_col])] = df.loc[i,name_col]
    return item_dict

def run_model(interactions, n_components=30, loss='warp', epoch=30, n_jobs = 4):
    '''
    Runs matrix-factorization model using LightFM
    Arguments:
        interactions = Pandas DataFrame containing user-item interactions
        n_components = number of desired embeddings to create to define item and user
        loss = loss function other options are logistic, brp
        epoch = number of epochs to run 
        n_jobs = number of cores used for execution 
    Returns:
        Model = Trained model
    '''
    x = sparse.csr_matrix(interactions.values)
    model = LightFM(no_components= n_components, loss=loss)
    model.fit(x,epochs=epoch,num_threads = n_jobs)
    return model

def get_recs(model, interactions, user_id, user_dict, 
                               item_dict,threshold = 0,num_items = 10, show_known = True, show_recs = True):
    '''
    Produces user recommendations
    Arguments:
        model = Trained matrix factorization model
        interactions = dataset used for training the model
        user_id = user ID for which we need to generate recommendation
        user_dict = Dictionary containing interaction_index as key and user_id as value
        item_dict = Dictionary containing item_id as key and item_name as value
        threshold = value above which the rating is favorable in new interaction matrix
        num_items = Number of recommendations to provide
        show_known (optional) - if True, prints known positives
        show_recs (optional) - if True, prints list of N recommended items  which user hopefully will be interested in
    Returns:
        list of titles user_id is predicted to be interested in 
    '''
    n_users, n_items = interactions.shape
    # Get value for user_id using dictionary
    user_x = user_dict[user_id]
    # Generate predictions
    scores = pd.Series(model.predict(user_x,np.arange(n_items)))
    # Get top predictions
    scores.index = interactions.columns
    scores = list(pd.Series(scores.sort_values(ascending=False).index))
    # Get list of known values
    known_items = list(pd.Series(interactions.loc[user_id,:] \
                                 [interactions.loc[user_id,:] > threshold].index).sort_values(ascending=False))
    # Ensure predictions are not already known
    scores = [x for x in scores if x not in known_items]
    # Take required number of items from prediction list
    return_score_list = scores[0:num_items]
    # Convert from item id to item name using item_dict
    known_items = list(pd.Series(known_items).apply(lambda x: item_dict[x]))
    scores = list(pd.Series(return_score_list).apply(lambda x: item_dict[x]))
    
    if show_known == True:
        print("Known Likes:")
        counter = 1
        for i in known_items:
            print(str(counter) + '- ' + i)
            counter+=1
            
    if show_recs == True:
        print("\n Recommended Items:")
        counter = 1
        for i in scores:
            print(str(counter) + '- ' + i)
            counter+=1
    return scores

def create_item_emdedding_matrix(model,interactions):
    '''
    Creates item-item distance embedding matrix
    Arguments:
        model = trained matrix factorization model
        interactions = dataset used for training the model
    Returns:
        Pandas dataframe containing cosine distance matrix between items
    '''
    df_item_norm_sparse = sparse.csr_matrix(model.item_embeddings)
    similarities = cosine_similarity(df_item_norm_sparse)
    item_emdedding_matrix = pd.DataFrame(similarities)
    item_emdedding_matrix.columns = interactions.columns
    item_emdedding_matrix.index = interactions.columns
    
    return item_emdedding_matrix

def get_item_recs(item_emdedding_matrix, item_id, 
                             item_dict, n_items = 10, show = True):
    '''
    Function to create item-item recommendation
    Arguments: 
        - item_emdedding_distance_matrix = Pandas dataframe containing cosine distance matrix b/w items
        - item_id  = item ID for which we need to generate recommended items
        - item_dict = Dictionary type input containing item_id as key and item_name as value
        - n_items = Number of items needed as an output
    Returns:
        - recommended_items = List of recommended items
    '''
    recommended_items = list(pd.Series(item_emdedding_matrix.loc[item_id,:]. \
                                  sort_values(ascending = False).head(n_items+1). \
                                  index[1:n_items+1]))
    if show == True:
        print("Item of interest: {0}".format(item_dict[item_id]))
        print("Similar items:")
        counter = 1
        for i in recommended_items:
            print(str(counter) + '- ' +  item_dict[i])
            counter+=1
    return recommended_items

def get_user_item_data():
    """
    Function that queries Athena for user-item interaction data. Return it as a dataframe.
    """
    conn = connect(s3_staging_dir="s3://boardgame-data/test-items/athena-results/",
                   region_name="us-east-1")
    
    query = "SELECT * FROM boardgame_app.boardgame_app_combined_user_data"
    
    df = pd.read_sql(query, conn)
    
    conn.close()
    
    return df

def get_item_data():
    """
    Function that queries Athena for item data. Return it as a dataframe.
    """
    conn = connect(s3_staging_dir="s3://boardgame-data/test-items/athena-results/",
                   region_name="us-east-1")
    
    query = "SELECT * FROM boardgame_app.boardgame_app_combined_data"
    
    df = pd.read_sql(query, conn)
    
    conn.close()
    
    return df

if __name__ == "__main__":
    # Example usage
    user_rating_df = get_user_item_data()
    item_df = get_item_data()
    interaction_matrix = create_interaction_matrix(user_rating_df, 'username', 'id', 'rating')
    print(interaction_matrix.shape)
    train_num = round((80/100)*len(interaction_matrix),0)
    print(f'We desire {train_num} users in our training set.')

    test_num = len(interaction_matrix)-train_num
    print(f'We desire {test_num} users in our test set.')

    train = interaction_matrix[:int(train_num)]
    test = interaction_matrix[int(train_num):]

    user_dict = create_user_dict(interaction_matrix)
    item_dict = create_item_dict(item_df, 'id', 'name')

    train_sparse = sparse.csr_matrix(train.values)
    #Add X users to Test so that the number of rows in Train match Test
    N = train.shape[0] #Rows in Train set
    n,m = test.shape #Rows & columns in Test set
    z = np.zeros([(N-n),m]) #Create the necessary rows of zeros with m columns
    #test = test.toarray() #Temporarily convert Test into a numpy array
    test = np.vstack((test,z)) #Vertically stack Test on top of the blank users
    test_sparse = sparse.csr_matrix(test) #Convert back to sparse

    model_warp = run_model(interactions=train, n_components=50, loss='warp', epoch=30, n_jobs=4)
    train_precision = precision_at_k(model_warp, train_sparse, k=10).mean()
    test_precision = precision_at_k(model_warp, test_sparse, k=10).mean()
    print(f'Warp Precision: train {train_precision:.2f}, test {test_precision:.2f}.')
    
    train_auc = auc_score(model_warp, train_sparse).mean()
    test_auc = auc_score(model_warp, test_sparse).mean()
    print('AUC: train %.2f, test %.2f.' % (train_auc, test_auc))

    model_bpr = run_model(interactions=train, n_components=50, loss='bpr', epoch=30, n_jobs=4)
    train_precision = precision_at_k(model_bpr, train_sparse, k=10).mean()
    test_precision = precision_at_k(model_bpr, test_sparse, k=10).mean()
    print(f'BPR Precision: train {train_precision:.2f}, test {test_precision:.2f}.')

    train_auc = auc_score(model_bpr, train_sparse).mean()
    test_auc = auc_score(model_bpr, test_sparse).mean()
    print('AUC: train %.2f, test %.2f.' % (train_auc, test_auc))


    model = run_model(interactions=interaction_matrix, n_components=50, loss='warp', epoch=30, n_jobs=4)
    
    username = 'bionicle4365'

    rec_list_u12 = get_recs(model = model, 
                    interactions = interaction_matrix, 
                    user_id = username, 
                    user_dict = user_dict,
                    item_dict = item_dict, 
                    threshold = 0,
                    num_items = 10,
                    show_known = True, 
                    show_recs = True)