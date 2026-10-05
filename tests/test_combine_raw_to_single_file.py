import os
import sys
from unittest.mock import MagicMock, patch
import pytest
import pyarrow as pa

# Add compactor folder to path so we can import the script
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_compactor'))
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
    mock_final_table.column_names = ['mechanics', 'categories']
    mock_final_table.column.side_effect = lambda col: MagicMock(to_pylist=MagicMock(return_value=[['Dice Rolling'], ['Card Game']]))
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
    
    # Check that upload_file was called to upload both the catalog and catalog_feature_frequencies to S3
    assert mock_s3.upload_file.call_count == 2
    mock_s3.upload_file.assert_any_call(
        Filename='/tmp/catalog.parquet',
        Bucket=bucket_name,
        Key='data/boardgames_combined/catalog.parquet'
    )
    mock_s3.upload_file.assert_any_call(
        Filename='/tmp/catalog_feature_frequencies.json',
        Bucket=bucket_name,
        Key='data/catalog_feature_frequencies.json'
    )

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

def test_generate_catalog_feature_frequencies_pure_pyarrow(tmp_path):
    schema = pa.schema([
        ('id', pa.string()),
        ('mechanics', pa.list_(pa.string())),
        ('categories', pa.list_(pa.string()))
    ])
    table = pa.Table.from_pydict({
        'id': ['1', '2', '3', '4'],
        'mechanics': [
            ['Dice Rolling', 'Hand Management'],
            ['Dice Rolling'],
            [],
            None
        ],
        'categories': [
            ['Card Game'],
            ['Card Game', 'Fantasy'],
            ['Fantasy'],
            None
        ]
    }, schema=schema)

    out_file = str(tmp_path / "test_freq.json")
    result = combine_raw_to_single_file.generate_catalog_feature_frequencies(table, output_path=out_file)

    assert result['total_games'] == 4
    assert result['mechanics'] == {'Dice Rolling': 2, 'Hand Management': 1}
    assert result['categories'] == {'Card Game': 2, 'Fantasy': 2}

    # Verify smoothed IDF: ln(1 + 4 / 2) = ln(3) ~= 1.0986
    # ln(1 + 4 / 1) = ln(5) ~= 1.6094
    import math
    assert result['mechanic_idf']['Dice Rolling'] == round(math.log(1.0 + 4 / 2), 4)
    assert result['mechanic_idf']['Hand Management'] == round(math.log(1.0 + 4 / 1), 4)
    assert result['category_idf']['Card Game'] == round(math.log(1.0 + 4 / 2), 4)
    assert 'generated_at' in result

    # Verify JSON file written to out_file
    assert os.path.exists(out_file)
    import json
    with open(out_file, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    assert loaded['total_games'] == 4

@patch('combine_raw_to_single_file.boto3.client')
@patch('combine_raw_to_single_file.pq.read_table')
@patch('combine_raw_to_single_file.pa.concat_tables')
@patch('combine_raw_to_single_file.pq.write_table')
def test_lambda_handler_user_compactor_skips_frequencies(mock_write_table, mock_concat_tables, mock_read_table, mock_boto_client):
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3

    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            'Contents': [
                {'Key': 'data/users/user1.parquet'}
            ]
        }
    ]

    mock_body = MagicMock()
    mock_body.__enter__.return_value.read.return_value = b'fake'
    mock_s3.get_object.return_value = {'Body': mock_body}

    mock_read_table.return_value = pa.Table.from_pydict({'username': ['alice']})
    mock_final_table = MagicMock()
    mock_final_table.num_rows = 1
    mock_final_table.num_columns = 1
    mock_concat_tables.return_value = mock_final_table

    event = {
        'raw_prefix': 'data/users/',
        'combined_prefix': 'data/users_combined/',
        'output_filename': 'users_combined.parquet',
        'apply_schema_alignment': False
    }
    response = combine_raw_to_single_file.lambda_handler(event, None)

    assert response['statusCode'] == 200
    assert "Successfully compacted 1 records into users_combined.parquet" in response['body']
    # upload_file should only be called once for users_combined.parquet, NOT for feature frequencies
    assert mock_s3.upload_file.call_count == 1
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    mock_s3.upload_file.assert_called_once_with(
        Filename='/tmp/catalog.parquet',
        Bucket=bucket_name,
        Key='data/users_combined/users_combined.parquet'
    )
