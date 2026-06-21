import os
import sys
from unittest.mock import MagicMock, patch
import pytest
import pyarrow as pa

# Add recommender folder to path so we can import the script
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_recommender'))
import combine_raw_to_single_file

@patch('combine_raw_to_single_file.boto3.client')
@patch('combine_raw_to_single_file.pq.read_table')
@patch('combine_raw_to_single_file.pa.concat_tables')
@patch('combine_raw_to_single_file.pq.write_table')
def test_lambda_handler_success(mock_write_table, mock_concat_tables, mock_read_table, mock_boto_client):
    # Setup mocks
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    
    # Mock paginator
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            'Contents': [
                {'Key': 'data/boardgames/1.parquet'},
                {'Key': 'data/boardgames/2.parquet'},
                {'Key': 'data/boardgames/catalog.parquet'}  # Should be filtered out
            ]
        }
    ]
    
    # Mock get_object
    mock_body = MagicMock()
    mock_body.__enter__.return_value.read.return_value = b'fake parquet bytes'
    mock_response = {'Body': mock_body}
    mock_s3.get_object.return_value = mock_response
    
    # Create a real small table with 8-column format to verify schema alignment works
    dummy_schema = pa.schema([
        ('id', pa.string()),
        ('type', pa.string()),
        ('name', pa.string()),
        ('max_players', pa.int32()),
        ('rating', pa.float64()),
        ('categories', pa.list_(pa.string())),
        ('mechanics', pa.list_(pa.string())),
        ('designers', pa.list_(pa.string()))
    ])
    real_table = pa.Table.from_pydict({
        'id': ['1'],
        'type': ['boardgame'],
        'name': ['Test Game'],
        'max_players': [4],
        'rating': [8.5],
        'categories': [['Theme']],
        'mechanics': [['Dice']],
        'designers': [['Designer']]
    }, schema=dummy_schema)
    mock_read_table.return_value = real_table
    
    # Mock concat_tables to return final table
    mock_final_table = MagicMock()
    mock_final_table.num_rows = 150
    mock_final_table.num_columns = 20
    mock_concat_tables.return_value = mock_final_table
    
    # Invoke lambda_handler
    event = {}
    context = None
    response = combine_raw_to_single_file.lambda_handler(event, context)
    
    # Assert success response
    assert response['statusCode'] == 200
    assert "Successfully compacted 150 records" in response['body']
    
    # Verify calls
    mock_s3.get_paginator.assert_called_once_with('list_objects_v2')
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    mock_paginator.paginate.assert_called_once_with(Bucket=bucket_name, Prefix='data/boardgames/')
    
    assert mock_s3.get_object.call_count == 2
    assert mock_read_table.call_count == 2
    
    # Check that put_object was called to write the catalog back to S3
    mock_s3.put_object.assert_called_once()
    _, kwargs = mock_s3.put_object.call_args
    assert kwargs['Bucket'] == bucket_name
    assert kwargs['Key'] == 'data/boardgames_combined/catalog.parquet'

@patch('combine_raw_to_single_file.boto3.client')
def test_lambda_handler_failure(mock_boto_client):
    # Setup mock to raise an exception
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    mock_s3.get_paginator.side_effect = Exception("S3 access denied")
    
    # Invoke lambda_handler
    event = {}
    context = None
    response = combine_raw_to_single_file.lambda_handler(event, context)
    
    # Assert error response
    assert response['statusCode'] == 500
    assert "Compaction failed: S3 access denied" in response['body']
