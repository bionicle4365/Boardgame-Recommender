import os
import sys
import json
from unittest.mock import MagicMock, patch
import pytest
from decimal import Decimal

# Set mock env variables BEFORE importing bgg_preferences_handler
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'mock-key'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'mock-secret'
os.environ['DYNAMODB_TABLE_NAME'] = 'bgg-user-preferences'
os.environ['DYNAMODB_CAFES_TABLE_NAME'] = 'bgg-cafes'
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'boardgame-app'
os.environ['USER_SQS_QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789012/test-queue'

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_preferences'))
import bgg_preferences_handler


SAMPLE_BGG_COLLECTION_XML = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<items totalitems="3" termsofuse="https://boardgamegeek.com/xmlapi/termsofuse" pubdate="Sun, 05 Oct 2026 12:00:00 +0000">
    <item objecttype="thing" objectid="13" subtype="boardgame" collid="101">
        <name sortindex="1">Catan</name>
        <yearpublished>1995</yearpublished>
        <status own="1" prevowned="0"/>
        <comment>Shelf A-2 (Main Library)</comment>
    </item>
    <item objecttype="thing" objectid="266192" subtype="boardgame" collid="102">
        <name sortindex="1">Wingspan</name>
        <yearpublished>2019</yearpublished>
        <status own="1" prevowned="0"/>
        <comment>Location: B-4</comment>
    </item>
    <item objecttype="thing" objectid="174430" subtype="boardgame" collid="103">
        <name sortindex="1">Gloomhaven</name>
        <yearpublished>2017</yearpublished>
        <status own="0" prevowned="1"/>
        <comment>Sold to friend</comment>
    </item>
</items>
"""

SAMPLE_BGG_ERROR_XML = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<errors>
    <error>
        <message>User does not exist</message>
    </error>
</errors>
"""

# ── 1. Validate BGG Tests ────────────────────────────────────────────────────

def test_validate_bgg_missing_username():
    event = {
        'rawPath': '/cafe/validate-bgg',
        'queryStringParameters': {}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'username query parameter is required' in body['error']


def test_validate_bgg_invalid_username_format():
    event = {
        'rawPath': '/cafe/validate-bgg',
        'queryStringParameters': {'username': 'invalid name with spaces!'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Invalid username format' in body['error']


def test_validate_bgg_invalid_regex():
    event = {
        'rawPath': '/cafe/validate-bgg',
        'queryStringParameters': {
            'username': 'maltandmeeple',
            'shelf_regex': '[unclosed-regex'
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Invalid shelf_regex' in body['error']


@patch('urllib.request.urlopen')
def test_validate_bgg_success(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = SAMPLE_BGG_COLLECTION_XML.encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    event = {
        'rawPath': '/cafe/validate-bgg',
        'queryStringParameters': {
            'username': 'maltandmeeple',
            'shelf_regex': r'(?:Shelf|Location|Bin):?\s*([A-Za-z0-9\-]+)'
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['username'] == 'maltandmeeple'
    assert body['total_owned'] == 2  # Catan (own=1) and Wingspan (own=1). Gloomhaven has own=0.
    assert body['shelf_tags_detected'] == 2
    assert len(body['sample_matches']) == 2
    assert body['sample_matches'][0]['name'] == 'Catan'
    assert body['sample_matches'][0]['extracted_location'] == 'A-2'
    assert body['sample_matches'][1]['name'] == 'Wingspan'
    assert body['sample_matches'][1]['extracted_location'] == 'B-4'


@patch('urllib.request.urlopen')
def test_validate_bgg_user_not_found(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = SAMPLE_BGG_ERROR_XML.encode('utf-8')
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    event = {
        'rawPath': '/cafe/validate-bgg',
        'queryStringParameters': {'username': 'nonexistent_cafe_user'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'User does not exist' in body['error']


# ── 2. Check Slug Tests ──────────────────────────────────────────────────────

def test_check_slug_missing():
    event = {
        'rawPath': '/cafe/check-slug',
        'queryStringParameters': {}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'slug query parameter is required' in body['error']


def test_check_slug_invalid_format():
    event = {
        'rawPath': '/cafe/check-slug',
        'queryStringParameters': {'slug': 'INVALID_SLUG!'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'Slug must be 3-50 lowercase' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_check_slug_available(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {}  # Item does not exist
    event = {
        'rawPath': '/cafe/check-slug',
        'queryStringParameters': {'slug': 'the-dice-box'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['available'] is True
    assert body['slug'] == 'the-dice-box'
    mock_cafes_table.get_item.assert_called_once_with(Key={'cafe_id': 'the-dice-box'})


@patch('bgg_preferences_handler.cafes_table')
def test_check_slug_already_taken(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {'cafe_id': 'the-dice-box', 'name': 'The Dice Box'}
    }
    event = {
        'rawPath': '/cafe/check-slug',
        'queryStringParameters': {'slug': 'the-dice-box'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['available'] is False
    assert body['slug'] == 'the-dice-box'


# ── 3. Cafe Onboard Tests ────────────────────────────────────────────────────

def test_cafe_onboard_unauthorized():
    event = {
        'rawPath': '/cafe/onboard',
        'requestContext': {},
        'body': json.dumps({'cafe_id': 'malt-and-meeple'})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'Unauthorized' in body['error']


def test_cafe_onboard_invalid_payload():
    event = {
        'rawPath': '/cafe/onboard',
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'cognito-user-123'}}}
        },
        'body': json.dumps({
            'cafe_id': 'bad slug!',
            'name': 'A',
            'bgg_username': ''
        })
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_onboard_slug_conflict(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'malt-and-meeple',
            'owner_cognito_id': 'different-owner-999'
        }
    }
    event = {
        'rawPath': '/cafe/onboard',
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'cognito-user-123'}}}
        },
        'body': json.dumps({
            'cafe_id': 'malt-and-meeple',
            'name': 'The Malt & Meeple',
            'bgg_username': 'maltmeeple',
            'table_count': 25
        })
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert 'already registered by another account' in body['error']


@patch('bgg_preferences_handler.cafes_table')
@patch('bgg_preferences_handler.s3')
@patch('boto3.client')
def test_cafe_onboard_success(mock_boto_client, mock_s3, mock_cafes_table):
    mock_cafes_table.get_item.return_value = {}  # Not taken
    mock_sqs = MagicMock()
    mock_boto_client.return_value = mock_sqs

    event = {
        'rawPath': '/cafe/onboard',
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'cognito-user-123'}}}
        },
        'body': json.dumps({
            'cafe_id': 'the-malt-and-meeple',
            'name': 'The Malt & Meeple',
            'bgg_username': 'maltandmeeple',
            'table_count': 20,
            'wifi_ssid': 'MaltGuest',
            'wifi_password': 'hopsandmeeples',
            'tagline': 'Craft beer & tabletop games in downtown.',
            'drink_pairings_enabled': True,
            'staff_pin': '9876'
        })
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['cafe']['cafe_id'] == 'the-malt-and-meeple'
    assert body['cafe']['name'] == 'The Malt & Meeple'
    assert body['cafe']['table_count'] == 20
    # Security: staff_pin must NOT be returned in public response
    assert 'staff_pin' not in body['cafe']

    # Verify DynamoDB persistence
    mock_cafes_table.put_item.assert_called_once()
    saved_item = mock_cafes_table.put_item.call_args[1]['Item']
    assert saved_item['cafe_id'] == 'the-malt-and-meeple'
    assert saved_item['owner_cognito_id'] == 'cognito-user-123'
    assert saved_item['table_count'] == 20
    assert saved_item['staff_pin'] == '9876'

    # Verify S3 mirror calls
    assert mock_s3.put_object.call_count >= 1

    # Verify SQS trigger
    mock_boto_client.assert_called_with('sqs', region_name='us-east-1')
    mock_sqs.send_message.assert_called_once()
    sqs_kwargs = mock_sqs.send_message.call_args[1]
    sent_payload = json.loads(sqs_kwargs['MessageBody'])
    assert sent_payload['username'] == 'maltandmeeple'
    assert sent_payload['cafe_id'] == 'the-malt-and-meeple'
    assert sent_payload['is_cafe'] is True



# ── 4. Cafe Meta & Collection Tests ───────────────────────────────────────────

def test_cafe_meta_missing_param():
    event = {
        'rawPath': '/cafe/meta',
        'queryStringParameters': {}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'cafe_id or slug' in body['error']


def test_cafe_collection_missing_param():
    event = {
        'rawPath': '/cafe/collection',
        'queryStringParameters': {}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'cafe_id or slug' in body['error']


@patch('bgg_preferences_handler.s3')
@patch('bgg_preferences_handler.cafes_table')
def test_cafe_collection_success(mock_cafes_table, mock_s3):
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq

    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-dice-box',
            'bgg_username': 'diceboxcafe'
        }
    }
    df_data = {
        'id': [13, 266192],
        'name': ['Catan', 'Wingspan'],
        'thumbnail': ['thumb1.jpg', 'thumb2.jpg'],
        'year_published': [1995, 2019],
        'rating': [7.1, 8.1],
        'complexity': [2.3, 2.4],
        'min_players': [3, 1],
        'max_players': [4, 5],
        'playing_time': [75, 60],
        'shelf_location': ['A-3', None]
    }
    table = pa.Table.from_pydict(df_data)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    parquet_bytes = sink.getvalue()

    mock_s3.get_object.return_value = {
        'Body': io.BytesIO(parquet_bytes)
    }

    event = {
        'rawPath': '/cafe/collection',
        'queryStringParameters': {'cafe_id': 'the-dice-box'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'ready'
    assert body['total'] == 2
    assert body['collection'][0]['name'] == 'Catan'
    assert body['collection'][0]['shelf_location'] == 'A-3'
    # Wingspan had None for shelf_location -> verify shelf_location omitted
    assert 'shelf_location' not in body['collection'][1]


@patch('bgg_preferences_handler._get_catalog_df')
@patch('bgg_preferences_handler.s3')
@patch('bgg_preferences_handler.cafes_table')
def test_cafe_collection_id_only_links_to_catalog(mock_cafes_table, mock_s3, mock_get_catalog_df):
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pandas as pd

    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-dice-box',
            'bgg_username': 'diceboxcafe'
        }
    }
    # Normalized cafe collection: ONLY id, shelf_location, own
    cafe_data = {
        'id': ['13', '266192'],
        'shelf_location': ['A-3', None],
        'own': [True, True]
    }
    table = pa.Table.from_pydict(cafe_data)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    parquet_bytes = sink.getvalue()

    mock_s3.get_object.return_value = {
        'Body': io.BytesIO(parquet_bytes)
    }

    # Master catalog DataFrame
    catalog_df = pd.DataFrame({
        'id': ['13', '266192', '999999'],
        'name': ['Catan', 'Wingspan', 'Other Game'],
        'thumbnail': ['thumb1.jpg', 'thumb2.jpg', 'thumb3.jpg'],
        'year_published': [1995, 2019, 2020],
        'rating': [7.1, 8.1, 6.5],
        'complexity': [2.3, 2.4, 3.0],
        'min_players': [3, 1, 2],
        'max_players': [4, 5, 4],
        'playing_time': [75, 60, 90],
        'rules_video_url': ['https://youtube.com/watch?v=catan123', None, None],
        'rules_video_id': ['catan123', None, None]
    })
    mock_get_catalog_df.return_value = catalog_df

    event = {
        'rawPath': '/cafe/collection',
        'queryStringParameters': {'cafe_id': 'the-dice-box'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'ready'
    assert body['total'] == 2
    assert body['collection'][0]['id'] == '13'
    assert body['collection'][0]['name'] == 'Catan'
    assert body['collection'][0]['shelf_location'] == 'A-3'
    assert body['collection'][0]['rules_video_url'] == 'https://youtube.com/watch?v=catan123'
    assert body['collection'][0]['rules_video_id'] == 'catan123'
    assert body['collection'][1]['id'] == '266192'
    assert body['collection'][1]['name'] == 'Wingspan'
    assert 'shelf_location' not in body['collection'][1]



@patch('bgg_preferences_handler.cafes_table')
def test_cafe_meta_not_found(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {}
    event = {
        'rawPath': '/cafe/meta',
        'queryStringParameters': {'cafe_id': 'unknown-cafe'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'not found' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_meta_success(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-dice-box',
            'name': 'The Dice Box',
            'slug': 'the-dice-box',
            'bgg_username': 'diceboxcafe',
            'table_count': Decimal('25'),
            'wifi_ssid': 'DiceBoxGuest',
            'wifi_password': 'rollinitiative',
            'tagline': 'Roll high!',
            'drink_pairings_enabled': True,
            'staff_pin': '1234',
            'owner_cognito_id': 'owner-123'
        }
    }
    event = {
        'rawPath': '/cafe/meta',
        'queryStringParameters': {'slug': 'the-dice-box'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['cafe_id'] == 'the-dice-box'
    assert body['name'] == 'The Dice Box'
    assert body['table_count'] == 25
    assert body['wifi_ssid'] == 'DiceBoxGuest'
    # Sensitive attributes omitted
    assert 'staff_pin' not in body
    assert 'owner_cognito_id' not in body


# ── 5. QR Code Generator Script Tests ────────────────────────────────────────

def test_generate_table_tents_bundle(tmp_path):
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
    import generate_cafe_table_qrs

    manifest = generate_cafe_table_qrs.generate_qr_bundle(
        cafe_id='test-bistro',
        name='Test Bistro',
        table_count=3,
        wifi_ssid='TestWifi',
        wifi_password='testpassword123',
        tagline='Play & drink!',
        output_dir=str(tmp_path)
    )

    assert manifest['cafe_id'] == 'test-bistro'
    assert manifest['table_count'] == 3
    assert len(manifest['tables']) == 3

    # Verify individual SVGs exist and contain table info
    for t in range(1, 4):
        svg_file = tmp_path / f"table_{t}.svg"
        assert svg_file.exists()
        content = svg_file.read_text(encoding='utf-8')
        assert f"TABLE {t}" in content
        assert "Test Bistro" in content
        assert "TestWifi" in content
        assert "testpassword123" in content

    # Verify master print sheet
    print_sheet = tmp_path / "print_all_tables.html"
    assert print_sheet.exists()
    sheet_content = print_sheet.read_text(encoding='utf-8')
    assert "Test Bistro" in sheet_content
    assert "TABLE 1" in sheet_content
    assert "TABLE 2" in sheet_content
    assert "TABLE 3" in sheet_content


def test_generate_qr_svg_path_fallback(tmp_path, monkeypatch):
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))
    import generate_cafe_table_qrs

    # Ensure fallback works when qrcode is None
    monkeypatch.setattr(generate_cafe_table_qrs, 'qrcode', None)
    view_box, path_d = generate_cafe_table_qrs.generate_qr_svg_path("https://www.meeplemanifesto.com/cafe/test?table=1")
    assert view_box == '0 0 350 350'
    assert len(path_d) > 0

    # Bundle generation succeeds even when qrcode library is not present
    manifest = generate_cafe_table_qrs.generate_qr_bundle(
        cafe_id='fallback-cafe',
        name='Fallback Cafe',
        table_count=1,
        output_dir=str(tmp_path)
    )
    assert manifest['cafe_id'] == 'fallback-cafe'
    assert (tmp_path / 'table_1.svg').exists()


