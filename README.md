# PDK.io API Integration & Collection Monitor

A comprehensive Python-based integration with the PDK.io API, providing functionality to manage cloud nodes, devices, and device control operations. This project includes utilities for device management and a Postman collection monitor for API endpoint reference.

## API Documentation

For complete API documentation and reference, visit:
[PDK.io API Documentation](https://developer.pdk.io/web/2.0/introduction)

## Project Structure

```
PDK.io/
├── credentials.json                    # API credentials (required)
├── token.db                           # Authentication token storage
├── collections.db                     # Postman collection history
├── postman_endpoint_list_collection.py # Postman collection API reference generator
├── test.py                            # Postman collection monitor
├── requirements.txt                   # Project dependencies
└── pdk_io_endpoints/
    ├── auth.py                       # Authentication and base API functionality
    ├── commands/                     # Device control operations
    │   ├── close_device.py          # Device close operation
    │   └── control_device.py        # Device open/close operations
    └── system_functions/            # System management
        ├── list_devices.py          # Device listing on a particular cloud node
        └── list_cloud_nodes.py       # Cloud nodes on a system
```

## Setup & Installation

1. Clone this repository:
```bash
git clone https://github.com/jamesputtmann/PDK.io.git
cd PDK.io
```

2. Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `credentials.json` file in the root directory:
```json
{
    "email": "your.email@example.com",
    "password": "your_password",
    "system_id": "your_system_id"
}
```

*Note: This user will need to be added to "Permissions" in the PDK.io front-facing UI/UX. Only Admin permission level users have been tested so far.*


## Core Features

### Postman Collection Monitor and API Reference Generator

The project includes two utilities to fetch and monitor the PDK.io API Postman collection:

1. `postman_endpoint_list_collection.py`: This tool helps developers:
    - Access and reference available API endpoints
    - Track changes in the API documentation
    - Generate local endpoint references for development
    - Monitor updates to the API specification

    Usage:
    ```bash
    python postman_endpoint_list_collection.py
    ```

2. `test.py`: This monitoring utility helps developers:
    - Fetch JSON from a specified URL with exponential backoff retry
    - Save the fetched collection to a local database
    - Compare the new collection with the previous version
    - Display comparison results with ASCII art

    Usage:
    ```bash
    python test.py
    ```

### Device Management Commands

1. **List Cloud Nodes and Devices**
```bash
python -m pdk_io_endpoints.system_functions.list_devices
python -m pdk_io_endpoints.system_functions.list_cloud_nodes
```
- Lists all available cloud nodes
- Displays devices on selected nodes
- Stores information in local database

2. **Control Devices (Open/Close)**
```bash
python -m pdk_io_endpoints.commands.control_device
```
- Unified interface for device control (open/close)
- Supports custom dwell time for open operations
- Includes activity history

3. **Dedicated Close Device**
```bash
python -m pdk_io_endpoints.commands.close_device
```
- Streamlined interface for closing devices
- Includes activity tracking

### Authentication System

The system includes a robust authentication framework:
- Token-based authentication with automatic refresh
- Secure token storage in SQLite
- Rate limit handling
- Session management

However, to ensure production readiness, additional testing and network request analysis are required. Without the properly provisioned API client and client secret, a refresh token cannot be obtained to exchange for future auth_tokens (ID tokens). We are conducting further testing to determine if any network requests can handle this without necessitating a full re-authentication (log-in). In the meantime, users may experience rate limitation.

### Database Management

The project uses two SQLite databases for managing different aspects of the system:

1. **Token Database** (`token.db`)

This database manages authentication tokens and stores system data across four main tables:

```sql
-- Authentication Tokens
-- Stores authentication and system tokens with their expiry information
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

-- Cloud Nodes Information
-- Maintains information about PDK cloud nodes including connection status
CREATE TABLE cloud_nodes (
    id TEXT PRIMARY KEY,
    name TEXT,
    serial_number TEXT,
    sync_status TEXT,
    connection_status TEXT,
    software_version TEXT,
    mac_address TEXT,
    ipv4_address TEXT,
    ipv6_address TEXT,
    last_updated TIMESTAMP
);

-- Devices Information
-- Stores comprehensive device configuration and status information
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    cloud_node_id TEXT,
    port INTEGER,
    delay INTEGER,
    dwell INTEGER,
    dps BOOLEAN,              -- Door Position Sensor status
    rex BOOLEAN,              -- Request to Exit status
    name TEXT,
    connection TEXT,
    forced_alarm BOOLEAN,
    auto_open_after_first_allow BOOLEAN,
    prop_alarm BOOLEAN,
    prop_delay INTEGER,
    firmware_version TEXT,
    hardware_version TEXT,
    serial_number TEXT,
    input_types TEXT,         -- JSON array of supported input types
    osdp_address INTEGER,
    partition TEXT,           -- JSON array of partition information
    authentication_policy TEXT,
    reader TEXT,              -- JSON object of reader configuration
    type TEXT,
    public_icon TEXT,
    reader_type TEXT,
    last_updated TIMESTAMP,
    FOREIGN KEY (cloud_node_id) REFERENCES cloud_nodes (id)
);

-- Gate Activity Logging
-- Tracks all gate operations and their outcomes
CREATE TABLE gate_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    cloud_node_id TEXT,
    action TEXT,              -- Type of action (OPEN/CLOSE)
    status TEXT,              -- Outcome status (SUCCESS/FAILED)
    response TEXT,            -- JSON object containing detailed response
    timestamp TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices (id),
    FOREIGN KEY (cloud_node_id) REFERENCES cloud_nodes (id)
);
```

2. **Collections Database** (`collections.db`)

This database tracks changes in the PDK.io API Postman collection:

```sql
CREATE TABLE collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,    -- When the collection was fetched
    collection_data JSON NOT NULL   -- Complete Postman collection data
);
```

## Development

### Adding New Endpoints
1. Reference the API documentation at [PDK.io Developer Portal](https://developer.pdk.io/web/2.0/introduction)
2. Use `postman_endpoint_list_collection.py` to view available endpoints
3. Create new endpoint files in appropriate directories
4. Implement endpoint logic following existing patterns

### Best Practices
- Use type hints for better code clarity
- Follow established logging patterns
- Implement proper error handling
- Document new endpoints

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes
4. Submit a pull request

## Support

For questions or issues:
1. Check the [PDK.io API Documentation](https://developer.pdk.io/web/2.0/introduction)
2. Review logged errors
3. Contact the development team

## License

This project is open source and requires PDK.io user credentials for usage. Please reach out to the appropriate administrator to obtain user credentials for a system. 

## Important Note

The system must be migrated to the PDK.io 2.0. Ensure that all endpoints and functionalities are compatible with the latest version of the PDK.io API. Refer to the [PDK.io 2.0 Migration Guide](https://developer.pdk.io/web/2.0/migration) for detailed instructions and best practices on how to perform the migration.
