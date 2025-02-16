# Postman Collection Change Detector

A Python utility that monitors changes in a Postman Collection by periodically downloading and comparing JSON files to detect changes in the collection. In hopes that the postman collection ("comprehansive") is updated simultaneous to the rest of the API documentation.

## Features

- Automatically downloads Postman Collection JSON from a the URL
- Stores collections efficiently in SQLite3 database with timestamps
- Compares the latest version with the previous version
- Maintains a searchable history of collection versions
- Logging with detailed change tracking

## Prerequisites

- Python 3.7 or higher
- Package manager (pip, uv, etc.)
- SQLite3 (usually comes with Python)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/jamesputtmann/PDK.io.git
cd PDK.io
```

2. Create and activate a virtual environment:
```bash
# Using venv
python3 -m venv .venv
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows

# Or using your preferred virtual environment tool
```

3. Install dependencies using your preferred package manager:

Using pip:
```bash
pip install -r requirements.txt
```

Using uv:
```bash
uv pip install -r requirements.txt
```

4. Initialize the SQLite database:
```bash
python -c "from test import init_db; init_db()"
```

## Usage

Run the script using Python:

```bash
python test.py
```

The script will:
1. Connect to or create the SQLite database if it doesn't exist
2. Download the latest Postman collection
3. Store it in the database with a timestamp
4. Compare it with the previous version
5. Log detailed changes if any are found

## Configuration

The following parameters can be modified in `test.py`:

- `url`: The URL of your Postman collection
- `db_path`: The path where the SQLite database will be stored (default: "collections.db")


## Database Schema

The SQLite database contains a single table `collections` with the following schema:

```sql
CREATE TABLE collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    collection_data JSON NOT NULL
);
```

## Project Structure

```
.
├── README.md
├── requirements.txt
├── .gitignore
├── test.py
├── auth.py          # Authentication and token management
├── test_endpoint.py # API endpoint implementation
├── collections.db   # Created on first run
└── token.db        # Authentication token storage
```

## Authentication System

The project includes a robust authentication system for interacting with the PDK.io API:

### Features

- Token-based authentication with automatic refresh
- Secure token storage in SQLite database
- Automatic token expiration handling
- Efficient token reuse and management
- Rate limit handling

### Components

#### 1. Authentication (`auth.py`)
- `TokenManager`: Handles secure token storage and retrieval
- `PDKAuth`: Manages the authentication flow
- `BaseAPI`: Base class for API endpoint implementations

#### 2. API Endpoints (`test_endpoint.py`)
- Built on top of the authentication system
- Implements specific API endpoints
- Automatic token management
- Error handling and logging

### Usage

1. Request credentials file from the author (required for authentication)
2. Place `credentials.json` in the project root
3. Initialize the endpoint handler:

```python
from test_endpoint import PDKEndpoint

# Initialize endpoint handler (handles auth automatically)
pdk = PDKEndpoint()

# Make API requests
nodes = pdk.list_cloud_nodes()
```

### Credentials

The `credentials.json` file is required for authentication but is not included in the repository for security reasons. Contact the author to obtain the necessary credentials. The file should contain:

```json
{
    "email": "your.email@example.com",
    "password": "your_password",
    "system_id": "your_system_id"
}
```

### Token Storage

Tokens are securely stored in `token.db` with the following schema:

```sql
CREATE TABLE tokens (
    system_id TEXT PRIMARY KEY,
    auth_token TEXT,
    access_token TEXT,
    system_token TEXT,
    auth_nonce TEXT,
    auth_token_expiry TIMESTAMP,
    system_token_expiry TIMESTAMP,
    last_updated TIMESTAMP
);
```


## Dynamic Endpoint Generation

The project includes a system for parsing and generating API endpoint references from the Postman collection. This functionality helps maintain up-to-date API endpoint documentation and provides a foundation for dynamic endpoint implementation.

### Features

- Automatic Postman collection parsing
- Structured endpoint reference generation
- Maintains original collection hierarchy
- JSON-formatted endpoint documentation
- Support for various request types and parameters

### Components

#### 1. Collection Parser (`dynamic_endpoint_generation.py`)
- `PostmanCollectionParser`: Handles collection fetching and parsing
- `APIEndpoint`: Base class for endpoint implementations
- Specialized API classes for different endpoint categories:
  - `CloudNodesAPI`
  - `DevicesAPI`
  - `ReportsAPI`
  - `HolderRulesAPI`

### Generated Structure

```
api_endpoints/
└── Postman_End_Point_References/
    ├── _collection_info.json
    ├── cloud_nodes/
    │   ├── list_cloud_nodes.json
    │   └── get_cloud_node.json
    ├── devices/
    │   └── open_device.json
    └── ...
```

### Endpoint Reference Format

Each endpoint is documented in a JSON file with the following structure:

```json
{
    "info": {
        "name": "Endpoint Name",
        "path": "category/endpoint",
        "created": "timestamp"
    },
    "request": {
        "method": "HTTP_METHOD",
        "url": "endpoint_url",
        "description": "Endpoint description",
        "headers": [
            {
                "key": "header_name",
                "value": "header_value"
            }
        ],
        "params": [
            {
                "key": "param_name",
                "value": "param_value"
            }
        ],
        "body": {
            // Request body schema
        }
    },
    "examples": [
        {
            "name": "Example name",
            "response": [
                // Example responses
            ]
        }
    ]
}
```

### Usage

1. Generate endpoint references:
```python
from dynamic_endpoint_generation import PostmanCollectionParser

# Initialize parser with collection URL
url = "https://developer.pdk.io/downloads/postman-collection-2.0.json"
parser = PostmanCollectionParser(url)

# Process collection and generate references
parser.process_collection()
```

2. Use with PDK authentication:
```python
from auth import BaseAPI
from typing import Dict, Any, Optional

class CustomEndpoint(BaseAPI):
    def my_endpoint(self, param1: str, param2: Optional[Dict] = None) -> Dict[str, Any]:
        return self.get('endpoint_path', params={'param1': param1, **param2 or {}})
```

### Future Potential

While currently used for reference generation, this system could be extended to:
- Automatically generate complete endpoint implementations
- Validate API responses against schemas
- Generate API client libraries
- Automate endpoint testing
- Create API documentation

Note: The dynamic generation of complete endpoints would require careful handling of:
- Authentication requirements
- Parameter validation
- Response processing
- Error handling
- Rate limiting

The current implementation focuses on providing accurate reference material for manual endpoint implementation while maintaining compatibility with the authentication system.