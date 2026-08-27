import os
import sys
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError

# Set mock env variables before import
os.environ['S3_BUCKET_NAME'] = 'test-bucket'
os.environ['S3_KEY'] = 'bgg-scraper/bgg_start_id.txt'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['SQS_QUEUE_NAME'] = 'bgg_game_data_scraper_queue'
os.environ['BATCH_SIZE'] = '2'
os.environ['S3_UPDATE_INTERVAL'] = '2'
os.environ['BGG_API_TOKEN'] = 'test-token'

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_game_scraper'))
import bgg_game_scraper

@patch('bgg_game_scraper.boto3.client')
@patch('requests.get')
@patch('time.sleep')
def test_main_success_flow(mock_sleep, mock_get, mock_boto):
    # Mock S3 Client
    mock_s3 = MagicMock()
    class MockNoSuchKey(Exception):
        pass
    mock_s3.exceptions.NoSuchKey = MockNoSuchKey
    
    mock_s3.get_object.return_value = {
        'Body': MagicMock(read=lambda: b"100\n")
    }
    
    # Mock SQS Client
    mock_sqs = MagicMock()
    mock_sqs.get_queue_url.return_value = {'QueueUrl': 'https://sqs.mock-queue'}
    
    # Associate clients with boto3.client
    def get_mock_client(service, *args, **kwargs):
        if service == 's3':
            return mock_s3
        if service == 'sqs':
            return mock_sqs
        return MagicMock()
    mock_boto.side_effect = get_mock_client

    # Mock requests.get BGG XML response for IDs 100, 101
    mock_xml = """
    <items>
        <item id="100" type="boardgame">
            <name type="primary" value="Catan"/>
        </item>
        <item id="101" type="rpg">
            <name type="primary" value="Dungeons &amp; Dragons"/>
        </item>
    </items>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = mock_xml.encode('utf-8')
    mock_get.return_value = mock_resp

    # Use sleep to break out of the infinite while True loop
    mock_sleep.side_effect = KeyboardInterrupt("Stop infinite loop")

    with pytest.raises(KeyboardInterrupt):
        bgg_game_scraper.main()

    # Verify start_id read from S3
    mock_s3.get_object.assert_called_once_with(Bucket='test-bucket', Key='bgg-scraper/bgg_start_id.txt')
    
    # Verify BGG API query
    mock_get.assert_called_once_with("https://boardgamegeek.com/xmlapi2/thing?id=100,101", headers={"Authorization": "Bearer test-token"})

    # Verify boardgame SQS send
    mock_sqs.send_message.assert_called_once_with(
        QueueUrl='https://sqs.mock-queue',
        MessageBody='100'
    )
    
    # Verify checkpoint S3 write (since update_counter (2) >= S3_UPDATE_INTERVAL (2))
    mock_s3.put_object.assert_called_once_with(
        Bucket='test-bucket',
        Key='bgg-scraper/bgg_start_id.txt',
        Body=b'102'
    )

@patch('bgg_game_scraper.boto3.client')
def test_main_s3_read_missing_key(mock_boto):
    mock_s3 = MagicMock()
    
    # Mock the s3.exceptions.NoSuchKey exception class to inherit from Exception
    class MockNoSuchKey(Exception):
        pass
    mock_s3.exceptions.NoSuchKey = MockNoSuchKey

    # Mock NoSuchKey error
    err_resp = {'Error': {'Code': 'NoSuchKey', 'Message': 'The specified key does not exist.'}}
    mock_s3.get_object.side_effect = ClientError(err_resp, 'GetObject')
    mock_boto.return_value = mock_s3

    with pytest.raises(SystemExit) as excinfo:
        bgg_game_scraper.main()
    assert excinfo.value.code == 1


@patch('bgg_game_scraper.boto3.client')
@patch('sys.argv', ['bgg_game_scraper', '--mode', 'reprocess'])
def test_main_reprocess_mode(mock_boto):
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            'Contents': [
                {'Key': 'data/boardgames/100.parquet'},
                {'Key': 'data/boardgames/200.parquet'},
                {'Key': 'data/boardgames/not_an_id.parquet'},
                {'Key': 'data/boardgames/'}
            ]
        }
    ]
    mock_s3.get_paginator.return_value = mock_paginator
    
    mock_sqs = MagicMock()
    mock_sqs.get_queue_url.return_value = {'QueueUrl': 'https://sqs.mock-queue'}
    
    def get_mock_client(service, *args, **kwargs):
        if service == 's3':
            return mock_s3
        if service == 'sqs':
            return mock_sqs
        return MagicMock()
    mock_boto.side_effect = get_mock_client
    
    # Run the scraper in reprocess mode
    bgg_game_scraper.main()
    
    # Verify S3 list_objects_v2 paginator was called
    mock_s3.get_paginator.assert_called_once_with('list_objects_v2')
    mock_paginator.paginate.assert_called_once_with(Bucket='test-bucket', Prefix='data/boardgames/')
    
    # Verify SQS send_message_batch was called with the extracted IDs
    mock_sqs.send_message_batch.assert_called_once_with(
        QueueUrl='https://sqs.mock-queue',
        Entries=[
            {'Id': '0', 'MessageBody': '100'},
            {'Id': '1', 'MessageBody': '200'}
        ]
    )


@patch('bgg_game_scraper.boto3.client')
@patch('sys.argv', ['bgg_game_scraper', '--mode', 'recent', '--window', '5'])
def test_main_recent_mode_custom_window(mock_boto):
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        'Body': MagicMock(read=lambda: b"100\n")
    }
    
    mock_sqs = MagicMock()
    mock_sqs.get_queue_url.return_value = {'QueueUrl': 'https://sqs.mock-queue'}
    
    def get_mock_client(service, *args, **kwargs):
        if service == 's3':
            return mock_s3
        if service == 'sqs':
            return mock_sqs
        return MagicMock()
    mock_boto.side_effect = get_mock_client
    
    # Run the scraper in recent mode with window=5
    bgg_game_scraper.main()
    
    # Verify start_id read from S3 checkpoint
    mock_s3.get_object.assert_called_once_with(Bucket='test-bucket', Key='bgg-scraper/bgg_start_id.txt')
    
    # Verify SQS send_message_batch was called with IDs 95 through 99
    expected_entries = [{'Id': str(idx), 'MessageBody': str(gid)} for idx, gid in enumerate(range(95, 100))]
    mock_sqs.send_message_batch.assert_called_once_with(
        QueueUrl='https://sqs.mock-queue',
        Entries=expected_entries
    )


@patch('bgg_game_scraper.boto3.client')
@patch('sys.argv', ['bgg_game_scraper', '--mode', 'recent', '--window', '2500'])
def test_main_recent_mode_clamping(mock_boto):
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        'Body': MagicMock(read=lambda: b"4\n")
    }
    
    mock_sqs = MagicMock()
    mock_sqs.get_queue_url.return_value = {'QueueUrl': 'https://sqs.mock-queue'}
    
    def get_mock_client(service, *args, **kwargs):
        if service == 's3':
            return mock_s3
        if service == 'sqs':
            return mock_sqs
        return MagicMock()
    mock_boto.side_effect = get_mock_client
    
    # Run the scraper with start_id=4 and window=2500 -> range 1..3
    bgg_game_scraper.main()
    
    expected_entries = [
        {'Id': '0', 'MessageBody': '1'},
        {'Id': '1', 'MessageBody': '2'},
        {'Id': '2', 'MessageBody': '3'}
    ]
    mock_sqs.send_message_batch.assert_called_once_with(
        QueueUrl='https://sqs.mock-queue',
        Entries=expected_entries
    )


@patch('bgg_game_scraper.boto3.client')
@patch('sys.argv', ['bgg_game_scraper', '--mode', 'recent'])
def test_main_recent_mode_s3_error(mock_boto):
    mock_s3 = MagicMock()
    class MockNoSuchKey(Exception):
        pass
    mock_s3.exceptions.NoSuchKey = MockNoSuchKey
    
    err_resp = {'Error': {'Code': 'NoSuchKey', 'Message': 'The specified key does not exist.'}}
    mock_s3.get_object.side_effect = ClientError(err_resp, 'GetObject')
    
    mock_sqs = MagicMock()
    mock_sqs.get_queue_url.return_value = {'QueueUrl': 'https://sqs.mock-queue'}
    
    def get_mock_client(service, *args, **kwargs):
        if service == 's3':
            return mock_s3
        if service == 'sqs':
            return mock_sqs
        return MagicMock()
    mock_boto.side_effect = get_mock_client
    
    with pytest.raises(SystemExit) as excinfo:
        bgg_game_scraper.main()
    assert excinfo.value.code == 1

