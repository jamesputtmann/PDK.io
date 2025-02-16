import json
import logging
from typing import Dict, Any, Optional
from auth import BaseAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PDKEndpoint')

class PDKEndpoint(BaseAPI):
    """PDK API endpoint handler"""
    
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
            
        return self.get('cloud-nodes', params=params)

def main():
    try:
        # Initialize PDK endpoint handler
        pdk = PDKEndpoint()
        
        # Test listing cloud nodes
        print("\n=== Testing Cloud Nodes Listing ===")
        result = pdk.list_cloud_nodes()
        
        # Pretty print the results
        print("\nCloud Nodes:")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main()
