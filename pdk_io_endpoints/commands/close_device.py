import json
import logging
from typing import Dict, Any, Optional, List
import requests
from ..system_functions.list_cloud_nodes import PDKEndpoint, BaseAPI
from ..system_functions.list_devices import PDKDeviceEndpoint
from .control_device import GateActivityManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKDeviceClose')

class PDKDeviceCloseEndpoint(BaseAPI):
    """PDK Device Close endpoint handler"""
    
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        # Properly initialize the base class first
        super().__init__(base_url)
        self.activity_manager = GateActivityManager()
    
    def close_device(self, cloud_node_id: str, device_id: str) -> bool:
        """Attempt to close a device.
        
        Args:
            cloud_node_id (str): ID of the cloud node
            device_id (str): ID of the device to control
            
        Returns:
            bool: True if operation was successful, False otherwise
        """
        # Get fresh system token
        self._refresh_if_needed()
        
        # Build endpoint URL
        endpoint = f"cloud-nodes/{cloud_node_id}/devices/{device_id}/close"
        url = f"{self.base_url}/{self.auth.system_id}/{endpoint.lstrip('/')}"
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {self.auth_data['system_token']}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        try:
            # Make request with proper authorization
            response = requests.post(url, headers=headers, json={})
            response.raise_for_status()
            
            # If we get here, the request was successful (204 No Content)
            success = True
            status = "SUCCESS"
            self.logger.info(f"Successfully closed device {device_id}")
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
        pdk_close = PDKDeviceCloseEndpoint()
        
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
                print(f"   IP: {node.get('ipv4Address', 'N/A')}")
            else:
                print(f"   Status: Disconnected")
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
            print("-" * 50)

            # Get device selection
            while True:
                try:
                    selection = input("\nEnter the number of the device to close (or 'q' to quit): ")
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

            # Confirm action
            confirm = input(f"\nAre you sure you want to close {selected_device['name']}? (y/n): ")
            if confirm.lower() != 'y':
                print("Operation cancelled.")
                return

            # Execute device close
            print(f"\n=== Closing Device: {selected_device['name']} ===")
            success = pdk_close.close_device(
                cloud_node_id=selected_node['id'],
                device_id=selected_device['id']
            )
            
            if success:
                print(f"\nSuccessfully closed {selected_device['name']}")
            else:
                print(f"\nFailed to close {selected_device['name']}")
            
            # Show recent activity
            activities = pdk_close.activity_manager.get_device_activity(selected_device['id'])
            print("\nRecent Device Activity:")
            print(json.dumps(activities[:5], indent=2))  # Show last 5 activities
            
        except Exception as e:
            print(f"Error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main() 