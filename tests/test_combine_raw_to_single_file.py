import os
import sys
from unittest.mock import MagicMock, patch
import pytest

# Add recommender folder to path so we can import the script
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_recommender'))
import combine_raw_to_single_file

@patch('combine_raw_to_single_file.fs.S3FileSystem')
@patch('combine_raw_to_single_file.ds.dataset')
@patch('combine_raw_to_single_file.pq.write_table')
def test_lambda_handler_success(mock_write_table, mock_dataset, mock_s3_fs):
    # Setup mock dataset to return a mock table
    mock_dataset_instance = MagicMock()
    mock_table = MagicMock()
    mock_table.num_rows = 150
    mock_table.num_columns = 10
    mock_dataset_instance.to_table.return_value = mock_table
    mock_dataset.return_value = mock_dataset_instance

    # Invoke lambda_handler
    event = {}
    context = None
    response = combine_raw_to_single_file.lambda_handler(event, context)

    # Assert success response
    assert response['statusCode'] == 200
    assert "Successfully compacted 150 records" in response['body']

    # Verify mocks were called correctly
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    mock_s3_fs.assert_called_once_with(region='us-east-1')
    
    mock_dataset.assert_called_once()
    args, kwargs = mock_dataset.call_args
    assert args[0] == f'{bucket_name}/data/boardgames/'
    assert kwargs['format'] == 'parquet'
    assert kwargs['filesystem'] == mock_s3_fs.return_value
    assert 'schema' in kwargs

    mock_write_table.assert_called_once_with(mock_table, f'{bucket_name}/data/boardgames_combined/catalog.parquet', filesystem=mock_s3_fs.return_value, compression='snappy')

@patch('combine_raw_to_single_file.fs.S3FileSystem')
@patch('combine_raw_to_single_file.ds.dataset')
def test_lambda_handler_failure(mock_dataset, mock_s3_fs):
    # Setup mock dataset to raise an exception
    mock_dataset.side_effect = Exception("S3 access denied")

    # Invoke lambda_handler
    event = {}
    context = None
    response = combine_raw_to_single_file.lambda_handler(event, context)

    # Assert error response
    assert response['statusCode'] == 500
    assert "Compaction failed: S3 access denied" in response['body']
