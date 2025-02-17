import json
import logging
import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from ..auth import BaseAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKEndpoint')

class CloudNodeManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Get the repo root directory (parent of pdk_io_endpoints)
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(repo_root, 'token.db')
        self.db_path = db_path
        self.logger = logging.getLogger('PDKEndpoint.CloudNodeManager')
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create cloud_nodes table if it doesn't exist"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cloud_nodes (
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
                )
            ''')
            conn.commit()
            self.logger.info("Cloud nodes table initialized successfully")
        except sqlite3.Error as e:
            self.logger.error(f"Database initialization error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def get_cloud_node_by_name(self, node_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cloud node by its name"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cloud_nodes WHERE name = ?', (node_name,))
            row = cursor.fetchone()

            if row:
                node = {
                    'id': row[0],
                    'name': row[1],
                    'serialNumber': row[2],
                    'syncStatus': json.loads(row[3]),
                    'connectionStatus': json.loads(row[4]),
                    'softwareVersion': json.loads(row[5]),
                    'macAddress': row[6],
                    'ipv4Address': row[7],
                    'ipv6Address': row[8],
                    'lastUpdated': row[9]
                }
                self.logger.info(f"Retrieved cloud node with name: {node_name}")
                return node
            else:
                self.logger.warning(f"No cloud node found with name: {node_name}")
                return None
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve cloud node by name: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def update_cloud_nodes(self, nodes: List[Dict[str, Any]]):
        """Update cloud nodes in the database"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.utcnow()

            for node in nodes:
                # Convert nested dictionaries to JSON strings
                sync_status = json.dumps(node.get('syncStatus', {}))
                connection_status = json.dumps(node.get('connectionStatus', {}))
                software_version = json.dumps(node.get('softwareVersion', {}))

                cursor.execute('''
                    INSERT OR REPLACE INTO cloud_nodes (
                        id, name, serial_number, sync_status, connection_status,
                        software_version, mac_address, ipv4_address, ipv6_address,
                        last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    node.get('id'),
                    node.get('name'),
                    node.get('serialNumber'),
                    sync_status,
                    connection_status,
                    software_version,
                    node.get('macAddress'),
                    node.get('ipv4Address'),
                    node.get('ipv6Address'),
                    now
                ))

            conn.commit()
            self.logger.info(f"Updated {len(nodes)} cloud nodes in database")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to update cloud nodes: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def get_cloud_nodes(self) -> List[Dict[str, Any]]:
        """Retrieve all cloud nodes from the database"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM cloud_nodes')
            rows = cursor.fetchall()

            nodes = []
            for row in rows:
                node = {
                    'id': row[0],
                    'name': row[1],
                    'serialNumber': row[2],
                    'syncStatus': json.loads(row[3]),
                    'connectionStatus': json.loads(row[4]),
                    'softwareVersion': json.loads(row[5]),
                    'macAddress': row[6],
                    'ipv4Address': row[7],
                    'ipv6Address': row[8],
                    'lastUpdated': row[9]
                }
                nodes.append(node)

            self.logger.info(f"Retrieved {len(nodes)} cloud nodes from database")
            return nodes
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve cloud nodes: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

class PDKEndpoint(BaseAPI):
    """PDK API endpoint handler"""
    
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        super().__init__(base_url)
        self.cloud_node_manager = CloudNodeManager()
    
    def list_cloud_nodes(self, page: Optional[int] = None, per_page: Optional[int] = None) -> Dict[str, Any]:
        """List all cloud nodes for the system.
        
        Args:
            page (int, optional): Zero-based page number for pagination (default: 0)
            per_page (int, optional): Number of items per page (default: 10, max: 100)
            
        Returns:
            Dict[str, Any]: Response containing array of cloud node objects
        """
        params = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
            
        result = self.get('cloud-nodes', params=params)
        
        # Update cloud nodes in database
        if isinstance(result, list):
            self.cloud_node_manager.update_cloud_nodes(result)
        
        return result

def main():
    try:
        # Initialize PDK endpoint handler
        pdk = PDKEndpoint()
        
        # Test listing cloud nodes and updating database
        print("\n=== Testing Cloud Nodes Listing and Database Update ===")
        cloud_nodes = pdk.list_cloud_nodes()
        
        # Pretty print the API results
        print("\nCloud Nodes from API:")
        print(json.dumps(cloud_nodes, indent=2))
        
        # Retrieve and display nodes from database
        print("\nCloud Nodes from Database:")
        db_nodes = pdk.cloud_node_manager.get_cloud_nodes()
        print(json.dumps(db_nodes, indent=2))
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main()
