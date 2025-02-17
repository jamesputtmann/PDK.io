import requests
import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from functools import wraps
from urllib.parse import urljoin

class APIEndpoint:
    """Base class for API endpoints"""
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def _make_request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make HTTP request with error handling"""
        url = urljoin(self.base_url, path)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"Request failed: {e}")
            raise

class CloudNodesAPI(APIEndpoint):
    """Cloud Nodes API endpoints"""
    
    def list_cloud_nodes(self, system_id: str) -> Dict:
        """List all cloud nodes for a system"""
        path = f"/{system_id}/cloud-nodes"
        return self._make_request("GET", path).json()
    
    def get_cloud_node(self, system_id: str, cloud_node_id: str) -> Dict:
        """Retrieve a specific cloud node"""
        path = f"/{system_id}/cloud-nodes/{cloud_node_id}"
        return self._make_request("GET", path).json()

class DevicesAPI(APIEndpoint):
    """Devices API endpoints"""
    
    def open_device(self, system_id: str, cloud_node_id: str, device_id: str) -> Dict:
        """Open a specific device"""
        path = f"/{system_id}/cloud-nodes/{cloud_node_id}/devices/{device_id}/open"
        return self._make_request("POST", path).json()

class ReportsAPI(APIEndpoint):
    """Reports API endpoints"""
    
    def export_report(self, system_id: str, report_filename: str, report_file_type: str) -> bytes:
        """Export a report file"""
        path = f"/{system_id}/reports/file/{report_filename}.{report_file_type}.zip"
        return self._make_request("GET", path).content

class HolderRulesAPI(APIEndpoint):
    """Holder Rules API endpoints"""
    
    def list_antipassback_restrictions(self, system_id: str, holder_id: str) -> Dict:
        """List all anti-passback restrictions for a holder"""
        path = f"/{system_id}/holders/{holder_id}/restrictions"
        return self._make_request("GET", path).json()

class PDKClient:
    """Main PDK API client"""
    def __init__(self, base_url: str = "https://systems.pdk.io"):
        self.cloud_nodes = CloudNodesAPI(base_url)
        self.devices = DevicesAPI(base_url)
        self.reports = ReportsAPI(base_url)
        self.holder_rules = HolderRulesAPI(base_url)

class PostmanCollectionParser:
    def __init__(self, url: str):
        """Initialize parser with Postman collection URL."""
        self.url = url
        self.output_dir = Path("api_endpoints")
        self.collection_data: Optional[Dict] = None

    def fetch_collection(self) -> bool:
        """Fetch Postman collection from URL."""
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            self.collection_data = response.json()
            return True
        except requests.RequestException as e:
            print(f"Failed to fetch collection: {e}")
            return False

    def _create_folder_structure(self) -> Path:
        """Create folder structure based on Postman collection folders."""
        # Create main output directory
        self.output_dir.mkdir(exist_ok=True)
        
        # Create or clear Postman references folder
        version_dir = self.output_dir / "Postman_End_Point_References"
        if version_dir.exists():
            # Remove directory and all its contents
            shutil.rmtree(version_dir)
        version_dir.mkdir()
        
        return version_dir

    def _parse_request(self, request: Dict) -> Dict[str, Any]:
        """Parse request details into structured format."""
        parsed = {
            'method': request.get('method', ''),
            'url': request.get('url', {}).get('raw', ''),
            'description': request.get('description', ''),
            'headers': [
                {'key': h['key'], 'value': h['value']} 
                for h in request.get('header', [])
            ],
            'params': [
                {'key': p['key'], 'value': p['value']} 
                for p in request.get('url', {}).get('query', [])
            ],
            'body': None
        }

        if 'body' in request:
            body = request['body']
            if body.get('mode') == 'raw':
                try:
                    parsed['body'] = json.loads(body.get('raw', '{}'))
                except json.JSONDecodeError:
                    parsed['body'] = body.get('raw')
            elif body.get('mode') == 'formdata':
                parsed['body'] = {
                    'formdata': [
                        {'key': f['key'], 'value': f['value'], 'type': f['type']}
                        for f in body.get('formdata', [])
                    ]
                }

        return parsed

    def _write_endpoint_file(self, folder_path: Path, name: str, data: Dict) -> None:
        """Write endpoint details to file with proper formatting."""
        # Create all parent directories
        folder_path.mkdir(parents=True, exist_ok=True)
        
        file_path = folder_path / f"{name}.json"
        with file_path.open('w') as f:
            json.dump(data, f, indent=2)

    def process_collection(self) -> None:
        """Process and save the Postman collection maintaining folder structure."""
        if not self.collection_data:
            if not self.fetch_collection():
                return

        version_dir = self._create_folder_structure()

        def process_items(items: List[Dict], current_path: Path):
            for item in items:
                if 'request' in item:  # This is an endpoint
                    request_data = self._parse_request(item['request'])
                    name = item.get('name', '').replace(' ', '_').lower()
                    
                    endpoint_data = {
                        'info': {
                            'name': item.get('name', ''),
                            'path': str(current_path.relative_to(version_dir)),
                            'created': datetime.now().isoformat()
                        },
                        'request': request_data,
                        'examples': [
                            {
                                'name': example.get('name', ''),
                                'response': example.get('response', [])
                            }
                            for example in item.get('response', [])
                        ]
                    }

                    self._write_endpoint_file(current_path, name, endpoint_data)

                elif 'item' in item:  # This is a folder
                    folder_name = item['name'].replace(' ', '_').lower()
                    new_path = current_path / folder_name
                    process_items(item['item'], new_path)

        # Start processing from root items
        process_items(self.collection_data['item'], version_dir)
        
        # Write collection info
        collection_info = {
            'name': self.collection_data.get('info', {}).get('name', ''),
            'description': self.collection_data.get('info', {}).get('description', ''),
            'schema': self.collection_data.get('info', {}).get('schema', ''),
            'version': datetime.now().strftime("%Y%m%d_%H%M%S"),
            'exported_at': datetime.now().isoformat()
        }
        self._write_endpoint_file(version_dir, '_collection_info', collection_info)

def main():
    """Main execution function."""
    url = "https://developer.pdk.io/downloads/postman-collection-2.0.json"
    parser = PostmanCollectionParser(url)
    parser.process_collection()

if __name__ == "__main__":
    main()