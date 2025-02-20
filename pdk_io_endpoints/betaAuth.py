import requests
import json
import urllib.parse
import time
import uuid
import sqlite3
import os
import logging
from datetime import datetime, timezone, UTC, timedelta
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKAuth')

# Logging configuration
VERBOSE_LOGGING = False  # Toggle for detailed logging

def log_step(step_name, message="", is_success=True, verbose_only=False):
    """Unified logging function for authentication steps"""
    if verbose_only and not VERBOSE_LOGGING:
        return
        
    status = "✓" if is_success else "✗"
    if not message:
        print(f"\n=== {step_name} {status} ===")
    else:
        if VERBOSE_LOGGING:
            print(f"{status} {step_name}: {message}")
        else:
            print(f"{status} {message}")

def log_token_summary(token_type, token_value, expiry=None):
    """Log a summary of token information"""
    if not token_value:
        print(f"  • {token_type}: Not available")
        return
        
    preview = token_value[:15] + "..." if len(token_value) > 15 else token_value
    if expiry:
        print(f"  • {token_type}: {preview} (Expires: {expiry.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        print(f"  • {token_type}: {preview}")

def log_request(method, url, status_code, cookies=None):
    """Log HTTP request details"""
    if not VERBOSE_LOGGING:
        return
        
    print(f"\n> {method} {url}")
    print(f"< Status: {status_code}")
    if cookies and VERBOSE_LOGGING:
        print("< Cookies:")
        for name, value in cookies.items():
            print(f"  {name}: {value[:20]}..." if value else f"  {name}: None")

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
    "client_id": "66df80e41f3e3361083b2941", # Beta client ID
}

# Environment configuration
ENV_CONFIG = {
    "beta": {
        "accounts_url": "https://betaaccounts.pdk.io",
        "api_url": "https://beta.pdk.io/api",
        "systems_url": "https://beta.pdk.io/systems",
        "callback_url": "https://beta.pdk.io/api/auth/callback"
    },
    "prod": {
        "accounts_url": "https://accounts.pdk.io",
        "api_url": "https://pdk.io/api",
        "systems_url": "https://pdk.io/systems", 
        "callback_url": "https://pdk.io/authCallback"
    }
}

# Set current environment
CURRENT_ENV = "beta"  # Can be switched to "prod" when going live

def adapt_datetime(dt):
    """Convert datetime to UTC string for SQLite storage"""
    return dt.astimezone(UTC).isoformat()

def convert_datetime(s):
    """Convert UTC string from SQLite back to datetime"""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    # Remove any quotes and 'b' prefix if present
    s = str(s).strip("'\"b")
    return datetime.fromisoformat(s)

# Register the datetime adapter and converter with SQLite
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("TIMESTAMP", convert_datetime)

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
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
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
                    refresh_token TEXT,
                    auth_nonce TEXT,
                    auth_token_expiry TIMESTAMP,
                    system_token_expiry TIMESTAMP,
                    refresh_token_expiry TIMESTAMP,
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
            now = datetime.now(UTC)
            auth_token_expiry = now + timedelta(minutes=5)  # ID token expires in 5 minutes
            system_token_expiry = now + timedelta(minutes=5)  # System token expires in 5 minutes
            refresh_token_expiry = now + timedelta(days=30)  # Refresh token lasts 30 days

            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO tokens 
                (system_id, auth_token, access_token, system_token, refresh_token,
                 auth_nonce, auth_token_expiry, system_token_expiry, 
                 refresh_token_expiry, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                auth_data['current_system_id'],
                auth_data.get('auth_token'),
                auth_data.get('access_token'),
                auth_data.get('system_token'),
                auth_data.get('refresh_token'),
                auth_data.get('auth_nonce'),
                auth_token_expiry,
                system_token_expiry,
                refresh_token_expiry,
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
            now = datetime.now(UTC)
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
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
            now = datetime.now(UTC)
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
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

    def get_valid_refresh_token(self, system_id):
        """Retrieve a valid refresh token for a given system_id"""
        conn = None
        try:
            now = datetime.now(UTC)
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT refresh_token FROM tokens 
                WHERE system_id = ? 
                AND refresh_token_expiry > ?
            ''', (system_id, now))
            result = cursor.fetchone()
            if result:
                self.logger.info(f"Retrieved valid refresh token for system {system_id}")
            else:
                self.logger.info(f"No valid refresh token found for system {system_id}")
            return result[0] if result else None
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve refresh token: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

class PDKAuth:
    def __init__(self):
        self.logger = logging.getLogger('PDKAuth.Core')
        # Base configuration
        self.base_url = ENV_CONFIG[CURRENT_ENV]["accounts_url"]
        self.client_id = USER_CONFIG["client_id"]
        self.system_id = USER_CONFIG["system_id"]
        self.redirect_uri = ENV_CONFIG[CURRENT_ENV]["callback_url"]
        
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

    def _prepare_refresh_headers(self, current_id_token=None, refresh_token=None):
        """Prepare headers for refresh token request"""
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Host": "beta.pdk.io",
            "Origin": "https://beta.pdk.io",
            "Referer": "https://beta.pdk.io/systems/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Google Chrome\";v=\"133\", \"Chromium\";v=\"133\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"macOS\""
        }

        # Prepare cookie string
        cookies = []
        if current_id_token:
            cookies.append(f"idToken={current_id_token}")
        if refresh_token:
            cookies.append(f"refreshToken={refresh_token}")
        
        # Add analytics cookies
        cookies.extend([
            "_ga=GA1.1.1951762571.1739391492",
            "__stripe_mid=20d98f72-074f-4a90-9979-1a0184234e74fa317a"
        ])
        
        headers["Cookie"] = "; ".join(cookies)
        return headers

    def refresh_system_token(self, auth_token):
        """Attempt to get a new system token using an existing auth token"""
        log_step("System Token Refresh", "Attempting to get new system token")
        
        api_headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/vnd.pdk.v2+json",
            "Origin": ENV_CONFIG[CURRENT_ENV]["api_url"],
            "Referer": f"{ENV_CONFIG[CURRENT_ENV]['systems_url']}/",
            "Content-Type": "application/json;charset=UTF-8"
        }
        
        system_token_url = f"{ENV_CONFIG[CURRENT_ENV]['api_url']}/auth/refresh/system/{self.system_id}"
        system_token_response = self.session.get(
            system_token_url, 
            headers=api_headers
        )
        
        log_request("GET", system_token_url, system_token_response.status_code)
        
        if system_token_response.status_code == 200:
            cookies = system_token_response.cookies
            system_token = cookies.get('systemToken')
            if system_token:
                log_step("System Token", "Successfully obtained new system token")
                return system_token
            else:
                log_step("System Token", "No system token in response cookies", is_success=False)
        else:
            log_step("System Token", f"Failed to get system token: {system_token_response.status_code}", is_success=False)
        
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
        """Get valid tokens following an efficient validation and refresh sequence:
        1. Check for valid system token
        2. If no valid system token, try to use valid auth token to get new system token
        3. If no valid auth token, try to use refresh token to get new auth token
        4. If all else fails, perform full authentication
        """
        try:
            log_step("Token Validation", "Starting token validation sequence")
            
            # Step 1: Check for valid system token
            tokens = self.token_manager.get_valid_tokens(self.system_id)
            if tokens:
                log_step("System Token", "Found valid system token")
                return {
                    "current_system_id": tokens[0],
                    "auth_token": tokens[1],
                    "access_token": tokens[2],
                    "system_token": tokens[3],
                    "refresh_token": tokens[4],
                    "auth_nonce": tokens[5]
                }
            
            # Step 2: Check for valid auth token
            auth_token = self.token_manager.get_valid_auth_token(self.system_id)
            if auth_token:
                log_step("Auth Token", "Found valid auth token, exchanging for system token")
                system_token = self.refresh_system_token(auth_token)
                if system_token:
                    log_step("System Token", "Successfully obtained new system token")
                    auth_data = {
                        "current_system_id": self.system_id,
                        "auth_token": auth_token,
                        "system_token": system_token
                    }
                    self.token_manager.store_tokens(auth_data)
                    return auth_data
                else:
                    log_step("System Token", "Failed to exchange auth token for system token", is_success=False)
            
            # Step 3: Try to use refresh token
            refresh_token = self.token_manager.get_valid_refresh_token(self.system_id)
            if refresh_token:
                log_step("Refresh Token", "Found valid refresh token, attempting token refresh")
                auth_data = self.refresh_tokens(refresh_token)
                if auth_data:
                    log_step("Token Refresh", "Successfully refreshed tokens")
                    self.token_manager.store_tokens(auth_data)
                    return auth_data
                else:
                    log_step("Token Refresh", "Failed to refresh tokens", is_success=False)
            
            # Step 4: If all else fails, perform full authentication
            log_step("Authentication", "No valid tokens available, performing full authentication")
            return self.login()
            
        except Exception as e:
            log_step("Token Validation", f"Error during token validation: {str(e)}", is_success=False)
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
        try:
            # Step 1: Initial profile check (will be unauthorized)
            log_step("Initial Profile Check", "Checking profile")
            profile_url = f"{self.base_url}/profile"
            profile_response = self.session.get(profile_url, headers=self.headers)
            log_request("GET", profile_url, profile_response.status_code)

            # Step 2: Pre-login local endpoint check
            log_step("Pre-login Check", "Checking local endpoint")
            local_auth_url = f"{self.base_url}/auth/local"
            local_check_response = self.session.get(local_auth_url, headers=self.headers)
            log_request("GET", local_auth_url, local_check_response.status_code)

            # Step 3: Submit login credentials
            log_step("Performing Login", "Submitting login credentials")
            login_payload = {"email": email, "password": password}
            login_response = self.session.post(local_auth_url, json=login_payload, headers=self.login_headers)
            log_request("POST", local_auth_url, login_response.status_code)
            
            if login_response.status_code == 429:
                log_step("Login", f"Rate limit exceeded: {login_response.text}", is_success=False)
                raise Exception("Rate limit exceeded")
            elif login_response.status_code != 200:
                log_step("Login", "Login failed", is_success=False)
                raise Exception("Login failed")

            # Step 4: Get profile after login
            log_step("Getting Profile", "Getting profile after login")
            profile_response = self.session.get(profile_url, headers=self.headers)
            log_request("GET", profile_url, profile_response.status_code)

            # Step 5: Get interaction ID
            log_step("Getting Interaction ID", "Getting interaction ID")
            oauth_params = {
                "response_type": "code",
                "scope": "openid offline_access",
                "prompt": "consent",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri
            }
            
            oauth_url = f"{self.base_url}/oauth2/auth"
            oauth_response = self.session.get(
                oauth_url, 
                params=oauth_params, 
                headers=self.oauth_headers, 
                allow_redirects=False
            )
            log_request("GET", oauth_url, oauth_response.status_code)
            
            if oauth_response.status_code == 302:
                location = oauth_response.headers.get('Location', '')
                interaction_id = location.split('/')[-1]
                log_step("Interaction ID", f"Interaction ID: {interaction_id}")
                
                # Step 6a: First interaction call
                log_step("First Interaction Call", "First interaction call")
                first_interaction_url = f"{self.base_url}/interaction/{interaction_id}"
                first_interaction_response = self.session.get(
                    first_interaction_url, 
                    headers=self.interaction_headers,
                    allow_redirects=False
                )
                log_request("GET", first_interaction_url, first_interaction_response.status_code)
                
                if first_interaction_response.status_code == 302:
                    # Step 6b: Second interaction call
                    log_step("Second Interaction Call", "Second interaction call")
                    second_interaction_url = f"{self.base_url}/oauth2/auth/{interaction_id}"
                    second_interaction_response = self.session.get(
                        second_interaction_url,
                        headers=self.interaction_headers,
                        allow_redirects=False
                    )
                    log_request("GET", second_interaction_url, second_interaction_response.status_code)
                    
                    if second_interaction_response.status_code == 302:
                        callback_url = second_interaction_response.headers.get('Location', '')
                        log_step("Callback URL", f"Callback URL: {callback_url}")
                        
                        # Step 8: Get tokens using the code
                        callback_headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                            "Accept-Language": "en-US,en;q=0.9",
                            "Connection": "keep-alive",
                            "Cookie": "_ga=GA1.1.1951762571.1739391492; __stripe_mid=20d98f72-074f-4a90-9979-1a0184234e74fa317a",
                            "Host": "beta.pdk.io",
                            "Referer": "https://betaaccounts.pdk.io/",
                            "Sec-Fetch-Dest": "document",
                            "Sec-Fetch-Mode": "navigate",
                            "Sec-Fetch-Site": "same-site",
                            "Sec-Fetch-User": "?1",
                            "Upgrade-Insecure-Requests": "1",
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Google Chrome\";v=\"133\", \"Chromium\";v=\"133\"",
                            "sec-ch-ua-mobile": "?0",
                            "sec-ch-ua-platform": "\"macOS\""
                        }

                        # First request to callback URL - this is a cross-domain request to beta.pdk.io
                        log_step("Exchanging Code for Tokens", "Exchanging code for tokens")
                        token_response = self.session.get(
                            callback_url,
                            headers=callback_headers,
                            allow_redirects=False  # Don't auto-follow redirects
                        )
                        log_request("GET", callback_url, token_response.status_code)

                        if token_response.status_code in [302, 307]:
                            # Get the redirect location and cookies
                            redirect_url = token_response.headers.get('Location')
                            log_step("Redirect URL", f"Redirect URL: {redirect_url}")
                            
                            # Extract and store cookies
                            id_token = token_response.cookies.get('idToken')
                            refresh_token = token_response.cookies.get('refreshToken')
                            
                            # Update session cookies
                            self.session.cookies.update(token_response.cookies)
                            
                            if id_token and refresh_token:
                                log_step("Tokens", "Successfully obtained tokens")
                                
                                # Step 9: Get system token
                                system_token = self.refresh_system_token(id_token)
                                
                                if system_token:
                                    log_step("System Token", "Successfully obtained system token")
                                    return {
                                        "current_system_id": self.system_id,
                                        "auth_token": id_token,
                                        "refresh_token": refresh_token,
                                        "system_token": system_token
                                    }
                            else:
                                log_step("Tokens", "Failed to obtain tokens from cookies", is_success=False)
                                if VERBOSE_LOGGING:
                                    print(f"Available cookies: {dict(token_response.cookies)}")
            
            log_step("Authentication", "Failed to complete authentication flow", is_success=False)
            raise Exception("Failed to complete authentication flow")
            
        except Exception as e:
            log_step("Login", f"Failed: {str(e)}", is_success=False)
            raise

    def refresh_tokens(self, refresh_token):
        """Refresh ID token using refresh token"""
        try:
            refresh_url = f"{ENV_CONFIG[CURRENT_ENV]['api_url']}/auth/refresh"
            log_step("Token Refresh", "Starting refresh process")
            
            # Get current ID token if available
            current_id_token = self.token_manager.get_valid_auth_token(self.system_id)
            if current_id_token:
                log_step("Current Token", "Found valid ID token to include", verbose_only=True)
            
            # Set up headers and make request
            headers = self._prepare_refresh_headers(current_id_token, refresh_token)
            log_step("Request Preparation", "Headers and cookies configured", verbose_only=True)
            
            refresh_response = self.session.get(refresh_url, headers=headers)
            log_request("GET", refresh_url, refresh_response.status_code, refresh_response.cookies)
            
            if refresh_response.status_code == 200:
                new_id_token = refresh_response.cookies.get('idToken')
                new_refresh_token = refresh_response.cookies.get('refreshToken')
                
                if new_id_token:
                    log_step("ID Token", "Successfully obtained new ID token")
                    log_token_summary("New ID Token", new_id_token)
                    
                    # Get new system token
                    log_step("System Token", "Requesting new system token")
                    system_token = self.refresh_system_token(new_id_token)
                    
                    if system_token:
                        log_step("System Token", "Successfully obtained new system token")
                        auth_data = {
                            "current_system_id": self.system_id,
                            "auth_token": new_id_token,
                            "refresh_token": new_refresh_token or refresh_token,
                            "system_token": system_token
                        }
                        
                        self.token_manager.store_tokens(auth_data)
                        log_step("Token Storage", "New tokens stored in database")
                        return auth_data
                    else:
                        log_step("System Token", "Failed to obtain new system token", is_success=False)
                else:
                    log_step("ID Token", "No new ID token in response", is_success=False)
                    if VERBOSE_LOGGING:
                        print(f"Available cookies: {dict(refresh_response.cookies)}")
            else:
                log_step("Refresh Request", f"Failed with status {refresh_response.status_code}", is_success=False)
                if VERBOSE_LOGGING:
                    print(f"Response content: {refresh_response.text}")
            
            return None
        except Exception as e:
            log_step("Token Refresh", f"Failed: {str(e)}", is_success=False)
            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                log_step("Error Details", e.response.text, is_success=False, verbose_only=True)
            return None

    def get_client_id(self):
        """Retrieve client_id from the login page"""
        log_step("Getting Client ID", "Retrieving client_id from login page")
        login_url = f"{self.base_url}/login"
        headers = self.headers.copy()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://accounts.pdk.io/login",
            "Upgrade-Insecure-Requests": "1"
        })
        
        response = self.session.get(login_url, headers=headers)
        log_request("GET", login_url, response.status_code)
        
        if response.status_code == 200:
            # Print the first 1000 characters of the response to see what we're getting
            log_step("Response Preview", "Printing response preview")
            print(response.text[:1000])
            
            soup = BeautifulSoup(response.text, 'html.parser')
            scripts = soup.find_all('script')
            log_step("Script Tags", f"Found {len(scripts)} script tags")
            
            for i, script in enumerate(scripts):
                log_step(f"Script {i + 1}", "Printing script content")
                if script.string:
                    log_step(f"Script {i + 1}", script.string[:200], verbose_only=True)  # Print first 200 chars of each script
                    if 'clientId' in script.string:
                        log_step(f"Script {i + 1}", "Found clientId in this script!", verbose_only=True)
                        log_step(f"Script {i + 1}", script.string, verbose_only=True)
        
        # For now, return the hardcoded value to keep things working
        self.client_id = USER_CONFIG["client_id"]
        return True

class BaseAPI:
    """Base class for PDK API endpoints with token management"""
    def __init__(self, base_url: str = None):
        self.logger = logging.getLogger('PDKAuth.BaseAPI')
        self.base_url = base_url or ENV_CONFIG[CURRENT_ENV]["systems_url"]
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
        """Make an authenticated API request"""
        # Ensure we have valid tokens
        self._refresh_if_needed()
        
        # Build URL
        url = f"{self.base_url}/{self.auth.system_id}/{endpoint.lstrip('/')}"
        
        # Prepare headers
        request_headers = {
            "Authorization": f"Bearer {self.auth_data['system_token']}",
            "Accept": "application/json",
            "Content-Type": "application/json;charset=UTF-8"
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
    """Main entry point with debug support"""
    parser = argparse.ArgumentParser(description='PDK Authentication Manager')
    parser.add_argument('--refresh', action='store_true', help='Force token refresh')
    parser.add_argument('--refresh-auth', action='store_true', help='Test refresh token exchange for new ID token')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()
    
    # Configure logging based on arguments
    if args.debug:
        logging.getLogger('PDKAuth').setLevel(logging.DEBUG)
        logging.getLogger('urllib3').setLevel(logging.DEBUG)
    
    global VERBOSE_LOGGING
    VERBOSE_LOGGING = args.verbose
    
    try:
        auth = PDKAuth()
        
        if args.refresh_auth:
            log_step("Auth Token Refresh", "Testing refresh token exchange for new ID token")
            # Get current refresh token
            refresh_token = auth.token_manager.get_valid_refresh_token(auth.system_id)
            if refresh_token:
                log_step("Refresh Token", "Found valid refresh token")
                log_token_summary("Current Refresh Token", refresh_token)
                
                # Attempt to exchange refresh token for new ID token
                auth_data = auth.refresh_tokens(refresh_token)
                if auth_data:
                    log_step("Token Exchange", "Successfully exchanged refresh token")
                    for key, value in auth_data.items():
                        if isinstance(value, str) and key.endswith('token'):
                            log_token_summary(key, value)
                else:
                    log_step("Token Exchange", "Failed to exchange refresh token", is_success=False)
            else:
                log_step("Refresh Token", "No valid refresh token found", is_success=False)
            return
            
        # Regular token management testing
        api = BaseAPI()
        log_step("Authentication", "Testing token management")
        
        if args.refresh:
            log_step("Token Refresh", "Testing refresh flow")
            # Force a token refresh
            api._refresh_if_needed()
            
        # Display current token state
        auth_data = api.auth_data
        if auth_data:
            log_step("Current Tokens")
            for key, value in auth_data.items():
                if isinstance(value, str) and key.endswith('token'):
                    log_token_summary(key, value)
                elif key != 'current_system_id':
                    print(f"  • {key}: {value}")
        
    except Exception as e:
        log_step("Error", str(e), is_success=False)
        if args.debug:
            import traceback
            traceback.print_exc()
        raise

if __name__ == "__main__":
    main()