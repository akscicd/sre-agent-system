"""
GCS Executor Tool - Executes Google Cloud Storage troubleshooting commands
"""

from google.cloud import storage
from typing import Dict, Any

class GCSExecutorTool:
    """Tool for executing GCS troubleshooting commands"""
    
    def __init__(self, project_id: str, dry_run: bool = True):
        self.project_id = project_id
        self.dry_run = dry_run
        self.storage_client = storage.Client(project=project_id)
        
    def execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GCS command"""
        action = command.get('action')
        
        if self.dry_run and action not in ['get_bucket_metadata', 'list_bucket_contents', 'get_bucket_iam']:
            return {
                'status': 'DRY_RUN',
                'message': f"Would execute: {action}",
                'command': command
            }
        
        try:
            if action == 'get_bucket_metadata':
                return self._get_bucket_metadata(command.get('bucket_name'))
            elif action == 'get_bucket_iam':
                return self._get_bucket_iam(command.get('bucket_name'))
            elif action == 'list_bucket_contents':
                return self._list_bucket_contents(command.get('bucket_name'), command.get('prefix'))
            elif action == 'enable_public_access_prevention':
                return self._enable_public_access_prevention(command.get('bucket_name'))
            else:
                return {'status': 'ERROR', 'message': f"Unknown action: {action}"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _get_bucket_metadata(self, bucket_name: str) -> Dict:
        """Get bucket metadata including versioning, location, and PAP status"""
        try:
            bucket = self.storage_client.get_bucket(bucket_name)
            return {
                'status': 'SUCCESS',
                'metadata': {
                    'name': bucket.name,
                    'location': bucket.location,
                    'storage_class': bucket.storage_class,
                    'versioning_enabled': bucket.versioning_enabled,
                    'public_access_prevention': bucket.iam_configuration.public_access_prevention,
                    'uniform_bucket_level_access': bucket.iam_configuration.uniform_bucket_level_access_enabled
                }
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _get_bucket_iam(self, bucket_name: str) -> Dict:
        """Get bucket IAM policy to check for public access or missing permissions"""
        try:
            bucket = self.storage_client.get_bucket(bucket_name)
            policy = bucket.get_iam_policy()
            bindings = []
            for binding in policy.bindings:
                bindings.append({
                    'role': binding['role'],
                    'members': list(binding['members'])
                })
            return {
                'status': 'SUCCESS',
                'iam_bindings': bindings
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _list_bucket_contents(self, bucket_name: str, prefix: str = None) -> Dict:
        """List objects in a bucket to check for missing files"""
        try:
            # Check if bucket exists first
            bucket = self.storage_client.get_bucket(bucket_name)
            blobs = list(self.storage_client.list_blobs(bucket_name, prefix=prefix, max_results=20))
            
            blob_list = []
            for blob in blobs:
                blob_list.append({
                    'name': blob.name,
                    'size': blob.size,
                    'updated': str(blob.updated)
                })
                
            return {
                'status': 'SUCCESS',
                'object_count': len(blob_list),
                'objects': blob_list
            }
        except Exception as e:
             return {'status': 'ERROR', 'message': str(e)}

    def _enable_public_access_prevention(self, bucket_name: str) -> Dict:
        """Enforce Public Access Prevention on the bucket"""
        try:
            bucket = self.storage_client.get_bucket(bucket_name)
            bucket.iam_configuration.public_access_prevention = "enforced"
            bucket.patch()
            return {
                'status': 'SUCCESS',
                'message': f"Public Access Prevention enforced on {bucket_name}"
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
