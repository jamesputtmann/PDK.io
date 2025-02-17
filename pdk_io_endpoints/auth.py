import requests
import json
import urllib.parse
import time
import uuid
import sqlite3
import os
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKAuth')

# Get the repo root directory (parent of pdk_io_endpoints)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load credentials from credentials.json
with open(os.path.join(REPO_ROOT, 'credentials.json')) as f:
    credentials = json.load(f)

# User configuration
USER_CONFIG = {
    "email": credentials["email"],
    "password": credentials["password"], 
    "system_id": credentials["system_id"],
    "client_id": "544557759a01deb9874c02ee", #this seems to be the same for all users and systems using this auth flow. We should probably check if this is the case for all users and systems.
}

class TokenManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(REPO_ROOT, 'token.db')
        self.db_path = db_path
        self.logger = logging.getLogger('PDKAuth.TokenManager')
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Check if database exists and initialize if it doesn't"""
        db_exists = os.path.exists(self.db_path)
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            if not db_exists:
                self.logger.info(f"Creating new database at {self.db_path}")
                self.init_db(conn)
            else:
                # Verify the table structure
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tokens'")
                if not cursor.fetchone():
                    self.logger.info("Database exists but tokens table missing. Creating table.")
                    self.init_db(conn)
        except sqlite3.Error as e:
            self.logger.error(f"Database initialization error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def init_db(self, conn):
        """Initialize the SQLite database with necessary tables"""
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tokens (
                    system_id TEXT PRIMARY KEY,
                    auth_token TEXT,
                    access_token TEXT,
                    system_token TEXT,
                    auth_nonce TEXT,
                    auth_token_expiry TIMESTAMP,
                    system_token_expiry TIMESTAMP,
                    last_updated TIMESTAMP
                )
            ''')
            conn.commit()
            self.logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to initialize database: {str(e)}")
            raise

    def store_tokens(self, auth_data):
        """Store token information in the database"""
        conn = None
        try:
            now = datetime.utcnow()
            auth_token_expiry = now + timedelta(minutes=5)
            system_token_expiry = now + timedelta(minutes=5)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO tokens 
                (system_id, auth_token, access_token, system_token, auth_nonce,
                 auth_token_expiry, system_token_expiry, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                auth_data['current_system_id'],
                auth_data['auth_token'],
                auth_data['access_token'],
                auth_data['system_token'],
                auth_data['auth_nonce'],
                auth_token_expiry,
                system_token_expiry,
                now
            ))
            conn.commit()
            self.logger.info(f"Stored tokens for system {auth_data['current_system_id']}")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to store tokens: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def get_valid_tokens(self, system_id):
        """Retrieve valid tokens for a given system_id"""
        conn = None
        try:
            now = datetime.utcnow()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM tokens 
                WHERE system_id = ? 
                AND system_token_expiry > ?
            ''', (system_id, now))
            result = cursor.fetchone()
            if result:
                self.logger.info(f"Retrieved valid tokens for system {system_id}")
            else:
                self.logger.info(f"No valid tokens found for system {system_id}")
            return result
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve tokens: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def get_valid_auth_token(self, system_id):
        """Retrieve a valid auth token for a given system_id"""
        conn = None
        try:
            now = datetime.utcnow()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT auth_token FROM tokens 
                WHERE system_id = ? 
                AND auth_token_expiry > ?
            ''', (system_id, now))
            result = cursor.fetchone()
            if result:
                self.logger.info(f"Retrieved valid auth token for system {system_id}")
            else:
                self.logger.info(f"No valid auth token found for system {system_id}")
            return result[0] if result else None
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve auth token: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

class PDKAuth:
    def __init__(self):
        self.logger = logging.getLogger('PDKAuth.Core')
        # Base configuration
        self.base_url = "https://accounts.pdk.io"
        self.client_id = USER_CONFIG["client_id"]
        self.system_id = USER_CONFIG["system_id"]
        self.redirect_uri = "https://pdk.io/authCallback"
        
        try:
            self.token_manager = TokenManager()
            self._initialize_session()
        except Exception as e:
            self.logger.error(f"Failed to initialize PDKAuth: {str(e)}")
            raise

    def _initialize_session(self):
        """Initialize session and headers"""
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Content-Type": "application/json;charset=UTF-8", 
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Google Chrome\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\""
        }

        # Common header variations
        self.login_headers = self.headers.copy()
        self.login_headers.update({
            "Origin": "https://accounts.pdk.io",
            "Referer": "https://accounts.pdk.io/login"
        })

        self.oauth_headers = self.headers.copy()
        self.oauth_headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://accounts.pdk.io/login",
            "Upgrade-Insecure-Requests": "1"
        })

        self.interaction_headers = self.headers.copy()
        self.interaction_headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://accounts.pdk.io/login",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate", 
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        })

    def refresh_system_token(self, auth_token):
        """Attempt to get a new system token using an existing auth token"""
        api_headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.pdk.v2+json",
            "Origin": "https://pdk.io",
            "Referer": "https://pdk.io/",
            "Content-Type": "application/json;charset=UTF-8"
        }
        
        system_token_url = f"{self.base_url}/api/systems/{self.system_id}/token"
        system_token_response = self.session.post(
            system_token_url, 
            headers=api_headers
        )
        
        if system_token_response.status_code == 200:
            return system_token_response.json().get('token')
        return None

    def initialize(self):
        """Ensure we have valid tokens, performing full authentication if necessary"""
        try:
            # First, try to get valid tokens from the database
            tokens = self.token_manager.get_valid_tokens(self.system_id)
            if not tokens:
                self.logger.info("No valid tokens found. Performing full authentication.")
                # Perform full authentication and store tokens
                auth_data = self.login()
                if not auth_data:
                    raise Exception("Failed to perform initial authentication")
                self.logger.info("Initial authentication successful")
                return auth_data
            return {
                "current_system_id": tokens[0],
                "auth_token": tokens[1],
                "access_token": tokens[2],
                "system_token": tokens[3],
                "auth_nonce": tokens[4]
            }
        except Exception as e:
            self.logger.error(f"Initialization failed: {str(e)}")
            raise

    def get_valid_tokens(self):
        """Get valid tokens or refresh/authenticate as needed"""
        try:
            # Check for valid tokens in database
            tokens = self.token_manager.get_valid_tokens(self.system_id)
            
            if tokens:
                self.logger.info("Using existing valid tokens")
                return {
                    "current_system_id": tokens[0],
                    "auth_token": tokens[1],
                    "access_token": tokens[2],
                    "system_token": tokens[3],
                    "auth_nonce": tokens[4]
                }

            # Check if we have a valid auth token to try refreshing system token
            auth_token = self.token_manager.get_valid_auth_token(self.system_id)
            if auth_token:
                self.logger.info("Attempting to refresh system token with valid auth token")
                system_token = self.refresh_system_token(auth_token)
                if system_token:
                    self.logger.info("Successfully refreshed system token")
                    auth_data = {
                        "current_system_id": self.system_id,
                        "auth_token": auth_token,
                        "access_token": None,
                        "system_token": system_token,
                        "auth_nonce": None
                    }
                    self.token_manager.store_tokens(auth_data)
                    return auth_data

            # If we get here, we need to perform a full authentication
            self.logger.info("Performing full authentication")
            return self.login()
        except Exception as e:
            self.logger.error(f"Error getting valid tokens: {str(e)}")
            raise

    def login(self, email=USER_CONFIG["email"], password=USER_CONFIG["password"]):
        """Perform full authentication flow and store tokens"""
        auth_data = self._perform_login(email, password)
        
        # Store the tokens
        if auth_data:
            self.token_manager.store_tokens(auth_data)
        
        return auth_data

    def _perform_login(self, email=USER_CONFIG["email"], password=USER_CONFIG["password"]):
        """Internal method to perform the actual login flow"""
        # Step 1: Initial login
        print("\n=== Performing Login ===")
        login_url = f"{self.base_url}/auth/local"
        login_payload = {"email": email, "password": password}
        
        login_response = self.session.post(login_url, json=login_payload, headers=self.login_headers)
        print(f"Login Status: {login_response.status_code}")
        
        if login_response.status_code == 429:
            print(f"Rate limit exceeded: {login_response.text}")
            exit()
        elif login_response.status_code != 200:
            raise Exception("Login failed")

        # Step 2: Get profile
        print("\n=== Getting Profile ===")
        profile_url = f"{self.base_url}/profile"
        profile_response = self.session.get(profile_url, headers=self.login_headers)
        print(f"Profile Status: {profile_response.status_code}")

        # Step 3: Get interaction ID
        print("\n=== Getting Interaction ID ===")
        nonce = ''.join(str(uuid.uuid4()).split('-'))[:32]
        oauth_params = {
            "response_type": "id_token token",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "nonce": nonce,
            "scope": "openid"
        }
        
        oauth_url = f"{self.base_url}/oauth2/auth"
        oauth_response = self.session.get(oauth_url, params=oauth_params, headers=self.oauth_headers, allow_redirects=False)
        print(f"OAuth Status: {oauth_response.status_code}")
        
        if oauth_response.status_code == 302:
            location = oauth_response.headers.get('Location', '')
            interaction_id = location.split('/')[-1]
            print(f"Interaction ID: {interaction_id}")
            
            # Step 4a: First interaction call
            print("\n=== First Interaction Call ===")
            first_interaction_url = f"{self.base_url}/interaction/{interaction_id}"
            
            first_interaction_response = self.session.get(
                first_interaction_url, 
                headers=self.interaction_headers,
                allow_redirects=False
            )
            print(f"First Interaction Status: {first_interaction_response.status_code}")
            
            if first_interaction_response.status_code == 302:
                # Step 4b: Second interaction call
                print("\n=== Second Interaction Call ===")
                second_interaction_url = f"{self.base_url}/oauth2/auth/{interaction_id}"
                
                second_interaction_response = self.session.get(
                    second_interaction_url,
                    headers=self.interaction_headers,
                    allow_redirects=False
                )
                print(f"Second Interaction Status: {second_interaction_response.status_code}")
                
                if second_interaction_response.status_code == 302:
                    callback_url = second_interaction_response.headers.get('Location', '')
                    print(f"Callback URL: {callback_url}")
                    
                    if '#' in callback_url:
                        fragment = callback_url.split('#')[1]
                        params = dict(param.split('=') for param in urllib.parse.unquote(fragment).split('&'))
                        
                        auth_token = params.get('id_token')
                        access_token = params.get('access_token')
                        
                        print(f"\nAuth Token Found: {'Yes' if auth_token else 'No'}")
                        print(f"Access Token Found: {'Yes' if access_token else 'No'}")
                        
                        # Step 5: Get system token using auth_token
                        if auth_token:
                            print("\n=== Getting System Token ===")
                            system_token = self.refresh_system_token(auth_token)
                            print(f"System Token Status: {system_token is not None}")
                            
                            if system_token:
                                auth_data = {
                                    "current_system_id": self.system_id,
                                    "auth_nonce": nonce,
                                    "auth_token": auth_token,
                                    "access_token": access_token,
                                    "system_token": system_token
                                }
                                return auth_data
        
        raise Exception("Failed to complete authentication flow")

    def get_client_id(self):
        """Retrieve client_id from the login page"""
        print("\n=== Getting Client ID ===")
        login_url = f"{self.base_url}/login"
        headers = self.headers.copy()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://accounts.pdk.io/login",
            "Upgrade-Insecure-Requests": "1"
        })
        
        response = self.session.get(login_url, headers=headers)
        print(f"Login page status: {response.status_code}")
        
        if response.status_code == 200:
            # Print the first 1000 characters of the response to see what we're getting
            print("Response preview:")
            print(response.text[:1000])
            
            soup = BeautifulSoup(response.text, 'html.parser')
            scripts = soup.find_all('script')
            print(f"\nFound {len(scripts)} script tags")
            
            for i, script in enumerate(scripts):
                print(f"\nScript {i + 1}:")
                if script.string:
                    print(script.string[:200])  # Print first 200 chars of each script
                    if 'clientId' in script.string:
                        print("Found clientId in this script!")
                        print(script.string)
        
        # For now, return the hardcoded value to keep things working
        self.client_id = USER_CONFIG["client_id"]
        return True

class BaseAPI:
    """Base class for PDK API endpoints with token management"""
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        self.logger = logging.getLogger('PDKAuth.BaseAPI')
        self.base_url = base_url
        self.auth = PDKAuth()
        self._ensure_authenticated()

    def _ensure_authenticated(self):
        """Ensure we have valid authentication tokens"""
        self.auth_data = self.auth.get_valid_tokens()
        if not self.auth_data or not self.auth_data.get('system_token'):
            raise Exception("Failed to obtain valid system token")

    def _refresh_if_needed(self):
        """Check and refresh tokens if necessary before making a request"""
        self.auth_data = self.auth.get_valid_tokens()

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                     data: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an authenticated API request
        
        Args:
            method (str): HTTP method (GET, POST, etc.)
            endpoint (str): API endpoint path
            params (dict, optional): Query parameters
            data (dict, optional): Request body data
            headers (dict, optional): Additional headers
            
        Returns:
            Dict[str, Any]: JSON response from the API
        """
        # Ensure we have valid tokens
        self._refresh_if_needed()
        
        # Build URL
        url = f"{self.base_url}/{self.auth.system_id}/{endpoint.lstrip('/')}"
        
        # Prepare headers
        request_headers = {
            "Authorization": f"Bearer {self.auth_data['system_token']}",
            "Accept": "application/json"
        }
        if headers:
            request_headers.update(headers)
            
        try:
            # Make the request
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=data if data else None,
                headers=request_headers
            )
            response.raise_for_status()
            
            # Log response headers for debugging
            self.logger.debug("Response Headers:")
            for header, value in response.headers.items():
                self.logger.debug(f"{header}: {value}")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error making {method} request to {endpoint}: {str(e)}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"Response content: {e.response.text}")
            raise

    def get(self, endpoint: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a GET request to the API"""
        return self._make_request("GET", endpoint, params=params, headers=headers)

    def post(self, endpoint: str, data: Dict, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a POST request to the API"""
        return self._make_request("POST", endpoint, params=params, data=data, headers=headers)

    def put(self, endpoint: str, data: Dict, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a PUT request to the API"""
        return self._make_request("PUT", endpoint, params=params, data=data, headers=headers)

    def delete(self, endpoint: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a DELETE request to the API"""
        return self._make_request("DELETE", endpoint, params=params, headers=headers)

def main():
    try:
        pdk_auth = PDKAuth()
        
        # Initialize and ensure we have valid tokens
        auth_data = pdk_auth.initialize()
        
        print("\n=== Initial Authentication Data ===")
        print(json.dumps(auth_data, indent=2))
        
        # Test token refresh
        time.sleep(2)  # Wait a bit
        print("\n=== Refreshing Tokens ===")
        auth_data = pdk_auth.get_valid_tokens()
        print(json.dumps(auth_data, indent=2))
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main()