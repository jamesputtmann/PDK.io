import requests
import json
import sqlite3
from datetime import datetime
from deepdiff import DeepDiff
import pyfiglet
import logging
import colorlog
import backoff
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from tqdm import tqdm
import time
import sys

def setup_logging():
    """Configure logging with color and file output."""
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(message)s%(reset)s',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    
    # Create handlers
    file_handler = logging.FileHandler(
        f'logs/collection_checker_{datetime.now().strftime("%Y%m%d")}.log'
    )
    file_handler.setFormatter(file_formatter)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    
    # Setup logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

class DatabaseManager:
    def __init__(self, db_path: str = "collections.db"):
        """Initialize database connection and create tables if they don't exist."""
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    collection_data JSON NOT NULL
                )
            """)
            conn.commit()

    def save_collection(self, collection_data: Dict[str, Any]) -> int:
        """Save a collection to the database and return its ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO collections (timestamp, collection_data) VALUES (?, ?)",
                (datetime.now().isoformat(), json.dumps(collection_data))
            )
            return cursor.lastrowid

    def get_latest_collections(self, limit: int = 2) -> list:
        """Retrieve the latest collections ordered by timestamp."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM collections ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            return [
                {
                    'id': row['id'],
                    'timestamp': row['timestamp'],
                    'collection_data': json.loads(row['collection_data'])
                }
                for row in cursor.fetchall()
            ]

class PostmanCollectionChecker:
    def __init__(self, url: str, db_manager: DatabaseManager):
        """Initialize the checker with URL and database manager."""
        self.url = url
        self.db_manager = db_manager

    @backoff.on_exception(
        backoff.expo,
        requests.exceptions.RequestException,
        max_tries=5
    )
    def fetch_collection(self) -> Optional[Dict[str, Any]]:
        """Fetch JSON from URL with exponential backoff retry."""
        try:
            with tqdm(total=1, desc="Collecting", unit="request", colour="green") as pbar:
                response = requests.get(self.url)
                response.raise_for_status()
                pbar.update(1)
                logger.info("Collection successfully fetched from API")
                return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch collection after retries: {e}")
            return None

    def compare_collections(self) -> None:
        """Fetch new collection, save to DB, and compare with previous version."""
        current_data = self.fetch_collection()
        if not current_data:
            return

        with tqdm(total=3, desc="Processing", unit="step", colour="blue") as pbar:
            # Save new collection
            collection_id = self.db_manager.save_collection(current_data)
            logger.info(f"New collection saved to database with ID: {collection_id}")
            pbar.update(1)
            
            # Get latest collections for comparison
            latest_collections = self.db_manager.get_latest_collections(2)
            pbar.update(1)
            
            if len(latest_collections) < 2:
                logger.info("No previous collection found for comparison")
                pbar.update(1)
                return

            # Compare current with previous
            diff = DeepDiff(
                latest_collections[1]['collection_data'],
                latest_collections[0]['collection_data'],
                ignore_order=True
            )
            pbar.update(1)
            
            self._display_results(diff)

    def _display_results(self, diff: DeepDiff) -> None:
        """Display comparison results with ASCII art."""
        if diff:
            # Log the comparison status to file
            logger.info("Status: Changes detected in collection")
            
            # Clear the line and display ASCII art
            sys.stdout.write("\033[K")  # Clear the line
            changes_text = pyfiglet.figlet_format("CHANGES DETECTED", font='standard')
            print("\n" + changes_text)
            
            # Log detailed changes to file only
            logger.info("Changes found:")
            for change_type, changes in diff.items():
                logger.info(f"\n{change_type}:")
                logger.info(json.dumps(changes, indent=2))
        else:
            # Log the comparison status to file
            logger.info("Status: No changes detected in collection")
            
            # Clear the line and display ASCII art
            sys.stdout.write("\033[K")  # Clear the line
            clear_text = pyfiglet.figlet_format("ALL CLEAR", font='standard')
            print("\n" + clear_text)

def init_db(db_path: str = "collections.db") -> None:
    """Initialize the database with schema."""
    DatabaseManager(db_path)
    logger.info(f"Database initialized at {db_path}")

def main():
    """Main execution function."""
    url = "https://developer.pdk.io/downloads/postman-collection-2.0.json"
    db_path = "collections.db"
    
    logger.info("Starting Postman Collection check...")
    
    db_manager = DatabaseManager(db_path)
    checker = PostmanCollectionChecker(url, db_manager)
    checker.compare_collections()
    
    logger.info("Check completed")

if __name__ == "__main__":
    main()