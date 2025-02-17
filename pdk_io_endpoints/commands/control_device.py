import json
import logging
import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from ..system_functions.list_cloud_nodes import PDKEndpoint, BaseAPI
from ..system_functions.list_devices import PDKDeviceEndpoint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKDeviceControl')

class GateActivityManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Get the repo root directory (parent of pdk_io_endpoints)
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(repo_root, 'token.db')
        self.db_path = db_path
        self.logger = logging.getLogger('PDKDeviceControl.GateActivityManager')
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create gate_activity table if it doesn't exist"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gate_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    cloud_node_id TEXT,
                    action TEXT,
                    status TEXT,
                    response TEXT,
                    timestamp TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices (id),
                    FOREIGN KEY (cloud_node_id) REFERENCES cloud_nodes (id)
                )
            ''')
            conn.commit()
            self.logger.info("Gate activity table initialized successfully")
        except sqlite3.Error as e:
            self.logger.error(f"Database initialization error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def log_activity(self, device_id: str, cloud_node_id: str, action: str, 
                    status: str, response: Dict[str, Any]):
        """Log a gate activity event"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.utcnow()

            cursor.execute('''
                INSERT INTO gate_activity (
                    device_id, cloud_node_id, action, status, response, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                device_id,
                cloud_node_id,
                action,
                status,
                json.dumps(response),
                now
            ))

            conn.commit()
            self.logger.info(f"Logged {action} activity for device {device_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Failed to log gate activity: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

    def get_device_activity(self, device_id: str) -> List[Dict[str, Any]]:
        """Retrieve activity history for a specific device"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM gate_activity 
                WHERE device_id = ? 
                ORDER BY timestamp DESC
            ''', (device_id,))
            rows = cursor.fetchall()

            activities = []
            for row in rows:
                activity = {
                    'id': row[0],
                    'deviceId': row[1],
                    'cloudNodeId': row[2],
                    'action': row[3],
                    'status': row[4],
                    'response': json.loads(row[5]),
                    'timestamp': row[6]
                }
                activities.append(activity)

            self.logger.info(f"Retrieved {len(activities)} activities for device {device_id}")
            return activities
        except sqlite3.Error as e:
            self.logger.error(f"Failed to retrieve gate activities: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()

class PDKDeviceControlEndpoint(BaseAPI):
    """PDK Device Control endpoint handler"""
    
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        super().__init__(base_url)
        self.activity_manager = GateActivityManager()
    
    def try_open_device(self, cloud_node_id: str, device_id: str, dwell: Optional[int] = None) -> bool:
        """Attempt to open a device.
        
        Args:
            cloud_node_id (str): ID of the cloud node
            device_id (str): ID of the device to control
            dwell (int, optional): Time in tenths of a second to keep device open (1-5400)
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        endpoint = f"cloud-nodes/{cloud_node_id}/devices/{device_id}/try-open"
        
        # Prepare request data
        data = {}
        if dwell is not None:
            if not 1 <= dwell <= 5400:
                raise ValueError("Dwell time must be between 1 and 5400 (tenths of a second)")
            data['dwell'] = dwell
            
        try:
            # Make raw request and check status code instead of parsing response
            response = self.session.post(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            
            # If we get here, the request was successful (204 No Content)
            success = True
            status = "SUCCESS"
        except Exception as e:
            self.logger.error(f"Failed to control device: {str(e)}")
            success = False
            status = "FAILED"
        
        # Log the activity
        self.activity_manager.log_activity(
            device_id=device_id,
            cloud_node_id=cloud_node_id,
            action="OPEN",
            status=status,
            response={"success": success, "dwell": dwell if dwell else "default"}
        )
        
        return success

    def close_device(self, cloud_node_id: str, device_id: str) -> bool:
        """Attempt to close a device.
        
        Args:
            cloud_node_id (str): ID of the cloud node
            device_id (str): ID of the device to control
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        endpoint = f"cloud-nodes/{cloud_node_id}/devices/{device_id}/close"
        
        try:
            # Make raw request and check status code instead of parsing response
            response = self.session.post(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                json={}
            )
            response.raise_for_status()
            
            # If we get here, the request was successful (204 No Content)
            success = True
            status = "SUCCESS"
        except Exception as e:
            self.logger.error(f"Failed to close device: {str(e)}")
            success = False
            status = "FAILED"
        
        # Log the activity
        self.activity_manager.log_activity(
            device_id=device_id,
            cloud_node_id=cloud_node_id,
            action="CLOSE",
            status=status,
            response={"success": success}
        )
        
        return success

def main():
    try:
        # Initialize all PDK endpoint handlers
        pdk = PDKEndpoint()
        pdk_devices = PDKDeviceEndpoint()
        pdk_control = PDKDeviceControlEndpoint()
        
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

        # Get cloud node selection
        while True:
            try:
                selection = input("\nEnter the number of the cloud node to control (or 'q' to quit): ")
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
            
            if not devices or len(devices) == 0:
                print("\nNo devices available on this node.")
                return

            # Display available devices
            print("\nAvailable Devices:")
            print("-" * 50)
            for idx, device in enumerate(devices, 1):
                print(f"{idx}. {device['name']} (Type: {device['type']})")
                print(f"   Hardware: {device['hardwareVersion']}")
                print(f"   Firmware: {device['firmwareVersion']}")
                print(f"   Default Dwell: {device.get('dwell', 'N/A')} (tenths of a second)")
            print("-" * 50)

            # Get device selection
            while True:
                try:
                    selection = input("\nEnter the number of the device to control (or 'q' to quit): ")
                    if selection.lower() == 'q':
                        print("Exiting...")
                        return
                    
                    idx = int(selection)
                    if 1 <= idx <= len(devices):
                        selected_device = devices[idx - 1]
                        break
                    else:
                        print(f"Please enter a number between 1 and {len(devices)}")
                except ValueError:
                    print("Please enter a valid number")

            # Get operation type
            while True:
                operation = input("\nWould you like to (o)pen or (c)lose the device? (o/c): ").lower()
                if operation in ['o', 'c']:
                    break
                print("Please enter 'o' for open or 'c' for close")

            if operation == 'o':
                # Get dwell time if desired
                dwell = None
                custom_dwell = input("\nWould you like to specify a custom dwell time? (y/n): ")
                if custom_dwell.lower() == 'y':
                    while True:
                        try:
                            dwell_input = input("Enter dwell time in tenths of a second (1-5400, or press Enter for default): ")
                            if not dwell_input:
                                break
                            dwell = int(dwell_input)
                            if 1 <= dwell <= 5400:
                                break
                            else:
                                print("Dwell time must be between 1 and 5400 (tenths of a second)")
                        except ValueError:
                            print("Please enter a valid number")

            # Confirm action
            action_word = "open" if operation == 'o' else "close"
            confirm = input(f"\nAre you sure you want to {action_word} {selected_device['name']}? (y/n): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                return

            # Execute device control
            print(f"\n=== {action_word.title()}ing Device: {selected_device['name']} ===")
            if operation == 'o':
                success = pdk_control.try_open_device(
                    cloud_node_id=selected_node['id'],
                    device_id=selected_device['id'],
                    dwell=dwell
                )
                if success:
                    print(f"\nSuccessfully opened {selected_device['name']}")
                    if dwell:
                        print(f"Device will remain open for {dwell/10:.1f} seconds")
                    else:
                        print("Using default dwell time")
                else:
                    print(f"\nFailed to open {selected_device['name']}")
            else:
                success = pdk_control.close_device(
                    cloud_node_id=selected_node['id'],
                    device_id=selected_device['id']
                )
                if success:
                    print(f"\nSuccessfully closed {selected_device['name']}")
                else:
                    print(f"\nFailed to close {selected_device['name']}")
            
            # Show recent activity
            activities = pdk_control.activity_manager.get_device_activity(selected_device['id'])
            print("\nRecent Device Activity:")
            print(json.dumps(activities[:5], indent=2))  # Show last 5 activities
            
        except Exception as e:
            print(f"Error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main() 