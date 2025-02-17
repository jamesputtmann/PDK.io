import json
import logging
import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from .list_cloud_nodes import PDKEndpoint, BaseAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKDevices')

class DeviceManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Get the repo root directory (parent of pdk_io_endpoints)
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(repo_root, 'token.db')
        self.db_path = db_path
        self.logger = logging.getLogger('PDKDevices.DeviceManager')
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create devices table if it doesn't exist"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    cloud_node_id TEXT,
                    port INTEGER,
                    delay INTEGER,
                    dwell INTEGER,
                    dps BOOLEAN,
                    rex BOOLEAN,
                    name TEXT,
                    connection TEXT,
                    forced_alarm BOOLEAN,
                    auto_open_after_first_allow BOOLEAN,
                    prop_alarm BOOLEAN,
                    prop_delay INTEGER,
                    firmware_version TEXT,
                    hardware_version TEXT,
                    serial_number TEXT,
                    input_types TEXT,
                    osdp_address INTEGER,
                    partition TEXT,
                    authentication_policy TEXT,
                    reader TEXT,
                    type TEXT,
                    public_icon TEXT,
                    reader_type TEXT,
                    last_updated TIMESTAMP,
                    FOREIGN KEY (cloud_node_id) REFERENCES cloud_nodes (id)
                )
            ''')
            conn.commit()
            self.logger.info("Devices table initialized successfully")
        except sqlite3.Error as e:
            self.logger.error(f"Database initialization error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def update_devices(self, cloud_node_id: str, devices: List[Dict[str, Any]]):
        """Update devices in the database for a specific cloud node"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.utcnow()

            for device in devices:
                # Convert lists and nested objects to JSON strings
                input_types = json.dumps(device.get('inputTypes', []))
                partition = json.dumps(device.get('partition', []))
                reader = json.dumps(device.get('reader'))

                cursor.execute('''
                    INSERT OR REPLACE INTO devices (
                        id, cloud_node_id, port, delay, dwell, dps, rex, name,
                        connection, forced_alarm, auto_open_after_first_allow,
                        prop_alarm, prop_delay, firmware_version, hardware_version,
                        serial_number, input_types, osdp_address, partition,
                        authentication_policy, reader, type, public_icon,
                        reader_type, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    device.get('id'),
                    cloud_node_id,
                    device.get('port'),
                    device.get('delay'),
                    device.get('dwell'),
                    device.get('dps'),
                    device.get('rex'),
                    device.get('name'),
                    device.get('connection'),
                    device.get('forcedAlarm'),
                    device.get('autoOpenAfterFirstAllow'),
                    device.get('propAlarm'),
                    device.get('propDelay'),
                    device.get('firmwareVersion'),
                    device.get('hardwareVersion'),
                    device.get('serialNumber'),
                    input_types,
                    device.get('osdpAddress'),
                    partition,
                    device.get('authenticationPolicy'),
                    reader,
                    device.get('type'),
                    device.get('publicIcon'),
                    device.get('readerType'),
                    now
                ))

            conn.commit()
            self.logger.info(f"Updated {len(devices)} devices for cloud node {cloud_node_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to update devices: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def get_devices_for_node(self, cloud_node_id: str) -> List[Dict[str, Any]]:
        """Retrieve all devices for a specific cloud node from the database"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM devices WHERE cloud_node_id = ?', (cloud_node_id,))
            rows = cursor.fetchall()

            devices = []
            for row in rows:
                device = {
                    'id': row[0],
                    'cloudNodeId': row[1],
                    'port': row[2],
                    'delay': row[3],
                    'dwell': row[4],
                    'dps': row[5],
                    'rex': row[6],
                    'name': row[7],
                    'connection': row[8],
                    'forcedAlarm': row[9],
                    'autoOpenAfterFirstAllow': row[10],
                    'propAlarm': row[11],
                    'propDelay': row[12],
                    'firmwareVersion': row[13],
                    'hardwareVersion': row[14],
                    'serialNumber': row[15],
                    'inputTypes': json.loads(row[16]),
                    'osdpAddress': row[17],
                    'partition': json.loads(row[18]),
                    'authenticationPolicy': row[19],
                    'reader': json.loads(row[20]),
                    'type': row[21],
                    'publicIcon': row[22],
                    'readerType': row[23],
                    'lastUpdated': row[24]
                }
                devices.append(device)

            self.logger.info(f"Retrieved {len(devices)} devices for cloud node {cloud_node_id}")
            return devices
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve devices: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

class PDKDeviceEndpoint(BaseAPI):
    """PDK Device endpoint handler"""
    
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        super().__init__(base_url)
        self.device_manager = DeviceManager()
    
    def list_devices_on_cloud_node(self, cloud_node_id: str, cloud_node_name: str) -> List[Dict[str, Any]]:
        """List all devices on a specific cloud node.
        
        Args:
            cloud_node_id (str): ID of the cloud node to list devices for
            cloud_node_name (str): Name of the cloud node (for logging)
            
        Returns:
            List[Dict[str, Any]]: List of device objects
        """
        # Get devices for the cloud node
        endpoint = f"cloud-nodes/{cloud_node_id}/devices"
        devices = self.get(endpoint)
        
        # Update devices in database
        if isinstance(devices, list):
            self.device_manager.update_devices(cloud_node_id, devices)
            self.logger.info(f"Updated {len(devices)} devices for cloud node: {cloud_node_name}")
        
        return devices

def main():
    try:
        # Initialize PDK endpoint handlers
        pdk = PDKEndpoint()
        pdk_devices = PDKDeviceEndpoint()
        
        # Refresh cloud nodes list
        print("\n=== Refreshing Cloud Nodes List ===")
        cloud_nodes = pdk.list_cloud_nodes()
        
        if not cloud_nodes or len(cloud_nodes) == 0:
            print("\nNo cloud nodes available.")
            return

        # Display available cloud nodes
        print("\nAvailable Cloud Nodes:")
        print("-" * 50)
        for idx, node in enumerate(cloud_nodes, 1):
            print(f"{idx}. {node['name']} ({node['serialNumber']})")
            if node.get('connectionStatus', {}).get('connected'):
                print(f"   Status: Connected")
            else:
                print(f"   Status: Disconnected")
            print(f"   IP: {node.get('ipv4Address', 'N/A')}")
        print("-" * 50)

        # Get user selection
        while True:
            try:
                selection = input("\nEnter the number of the cloud node to query (or 'q' to quit): ")
                if selection.lower() == 'q':
                    print("Exiting...")
                    return
                
                idx = int(selection)
                if 1 <= idx <= len(cloud_nodes):
                    selected_node = cloud_nodes[idx - 1]
                    break
                else:
                    print(f"Please enter a number between 1 and {len(cloud_nodes)}")
            except ValueError:
                print("Please enter a valid number")

        # Get devices for selected node
        print(f"\n=== Getting Devices for: {selected_node['name']} ===")
        try:
            devices = pdk_devices.list_devices_on_cloud_node(
                selected_node['id'],
                selected_node['name']
            )
            
            # Display devices from database to verify storage
            db_devices = pdk_devices.device_manager.get_devices_for_node(selected_node['id'])
            
            print("\nDevices on Cloud Node (from API):")
            print(json.dumps(devices, indent=2))
            print("\nDevices in Database:")
            print(json.dumps(db_devices, indent=2))
            
        except ValueError as e:
            print(f"Error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main() 