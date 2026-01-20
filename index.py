"""
Simplified API server using Supabase REST API (no direct PostgreSQL connection needed)
This avoids SSL/connection issues by using HTTP requests to Supabase
Vercel-compatible entry point
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import requests
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Simple CORS - allow all origins
CORS(app, origins="*")

# Add before_request to handle CORS for all requests
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({'status': 'ok'})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response, 200

# Configuration
API_TOKEN_EXPIRY = 3600  # 1 hour
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.warning("SUPABASE_URL and SUPABASE_KEY not set - using memory storage only")

# In-memory token store (for testing - use Supabase for production)
TOKEN_STORE = {}

def store_token_in_memory(token, stream_url, media_type, media_id, media_title, season_number, episode_number, description=None):
    """Store token in memory (for testing)"""
    TOKEN_STORE[token] = {
        'stream_url': stream_url,
        'media_type': media_type,
        'media_id': media_id,
        'media_title': media_title,
        'season_number': season_number,
        'episode_number': episode_number,
        'description': description,
        'created_at': datetime.utcnow().isoformat(),
        'expires_at': (datetime.utcnow() + timedelta(seconds=API_TOKEN_EXPIRY)).isoformat(),
        'accessed_count': 0
    }

def store_token_in_supabase(token, stream_url, media_type, media_id, media_title, season_number, episode_number, description=None):
    """Store token in Supabase using REST API"""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return False
        
        headers = {
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
        }
        
        data = {
            'token': token,
            'stream_url': stream_url,
            'media_type': media_type,
            'media_id': media_id,
            'media_title': media_title,
            'season_number': season_number,
            'episode_number': episode_number,
            'description': description,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=API_TOKEN_EXPIRY)).isoformat(),
            'accessed_count': 0
        }
        
        response = requests.post(
            f'{SUPABASE_URL}/rest/v1/stream_urls',
            headers=headers,
            json=data,
            timeout=5
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Token stored in Supabase: {token[:8]}...")
            return True
        else:
            logger.warning(f"Failed to store in Supabase: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.warning(f"Supabase storage failed: {e}. Using in-memory storage.")
        return False

def retrieve_token_from_memory(token):
    """Retrieve token from memory"""
    if token in TOKEN_STORE:
        data = TOKEN_STORE[token]
        if datetime.fromisoformat(data['expires_at']) > datetime.utcnow():
            data['accessed_count'] += 1
            return data
    return None

def retrieve_token_from_supabase(token):
    """Retrieve token from Supabase using REST API"""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        
        headers = {
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(
            f'{SUPABASE_URL}/rest/v1/stream_urls?token=eq.{token}',
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0]
        
        return None
        
    except Exception as e:
        logger.warning(f"Supabase retrieval failed: {e}")
        return None

@app.route('/', methods=['GET'])
def index():
    """API info endpoint"""
    return jsonify({
        'name': 'Tuniwix Stream Token API (Simplified)',
        'version': '2.0.0',
        'status': 'running',
        'storage': 'Supabase REST API + Memory Fallback',
        'endpoints': {
            'POST /api/generate-token': 'Generate a token for a stream URL',
            'GET /api/get-url/<token>': 'Retrieve stream URL using token',
            'GET /api/health': 'Check API health',
        }
    }), 200

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'API running',
        'storage': 'Hybrid (Supabase + Memory)',
        'tokens_in_memory': len(TOKEN_STORE)
    }), 200

@app.route('/api/generate-token', methods=['POST', 'OPTIONS'])
def api_generate_token():
    """Generate a token for a stream URL"""
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        
        if not data or 'stream_url' not in data or 'media_type' not in data or 'media_id' not in data:
            return jsonify({'error': 'Missing required fields: stream_url, media_type, media_id'}), 400
        
        # Generate unique token
        token = str(uuid.uuid4())
        
        stream_url = data.get('stream_url')
        media_type = data.get('media_type')
        media_id = data.get('media_id')
        media_title = data.get('media_title', 'Unknown')
        season_number = data.get('season_number')
        episode_number = data.get('episode_number')
        description = data.get('description')
        
        # Try to store in Supabase first, fallback to memory
        supabase_success = store_token_in_supabase(
            token, stream_url, media_type, media_id, media_title, season_number, episode_number, description
        )
        
        if not supabase_success:
            store_token_in_memory(
                token, stream_url, media_type, media_id, media_title, season_number, episode_number, description
            )
        
        logger.info(f"Generated token: {token[:8]}... for {media_type} ID:{media_id}")
        
        return jsonify({
            'success': True,
            'token': token,
            'expires_in': API_TOKEN_EXPIRY,
            'storage': 'Supabase' if supabase_success else 'Memory'
        }), 200
        
    except Exception as e:
        logger.error(f"Error in generate-token: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/get-url/<token>', methods=['GET', 'OPTIONS'])
def api_get_url(token):
    """Retrieve stream URL using token"""
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        # Try Supabase first
        result = retrieve_token_from_supabase(token)
        
        # Fallback to memory
        if not result:
            result = retrieve_token_from_memory(token)
        
        if not result:
            return jsonify({'error': 'Invalid or expired token'}), 404
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in get-url: {e}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"Server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# For local development
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
