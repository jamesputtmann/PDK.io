# Postman Collection Change Detector

A professional Python utility that monitors changes in a Postman Collection by periodically downloading and comparing JSON files. It provides visual feedback using ASCII art to indicate whether changes have been detected, with efficient SQLite3 storage for historical tracking.

## Features

- Automatically downloads Postman Collection JSON from a specified URL
- Stores collections efficiently in SQLite3 database with timestamps
- Compares the latest version with the previous version
- Displays ASCII art to clearly indicate if changes were detected
- Maintains a searchable history of collection versions
- Professional logging with detailed change tracking
- Type hints and modern Python practices

## Prerequisites

- Python 3.7 or higher
- Package manager (pip, uv, etc.)
- SQLite3 (usually comes with Python)

## Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd <repository-name>
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
5. Display ASCII art indicating whether changes were detected
6. Log detailed changes if any are found

## Configuration

The following parameters can be modified in `test.py`:

- `url`: The URL of your Postman collection
- `db_path`: The path where the SQLite database will be stored (default: "collections.db")

## Project Structure

```
.
├── README.md
├── requirements.txt
├── .gitignore
├── test.py
└── collections.db    # Created on first run
```

## Database Schema

The SQLite database contains a single table `collections` with the following schema:

```sql
CREATE TABLE collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    collection_data JSON NOT NULL
);
```

## Development

This project follows these best practices:
- Type hints for better code maintainability
- Context managers for database connections
- Comprehensive error handling
- Detailed logging
- Clean code structure with separation of concerns

## License

[Your chosen license]