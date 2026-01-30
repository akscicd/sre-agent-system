"""
GKE Executor Tool - Executes Kubernetes Engine commands
"""

from google.cloud import container_v1
from google.cloud import container_v1
from typing import Dict, Any
import subprocess
import json

class GKEExecutorTool:
    """Tool for executing GKE troubleshooting commands"""
    
    def __init__(self, project_id: str, dry_run: bool = True):
        self.project_id = project_id
        self.dry_run = dry_run
        self.cluster_manager_client = container_v1.ClusterManagerClient()
        
    def execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GKE command"""
        action = command.get('action')
        
        if self.dry_run:
            return {
                'status': 'DRY_RUN',
                'message': f"Would execute: {action}",
                'command': command
            }
        
        try:
            if action == 'get_cluster_info':
                return self._get_cluster_info(command.get('location'), command.get('cluster_name'))
            elif action == 'get_node_pools':
                return self._get_node_pools(command.get('location'), command.get('cluster_name'))
            elif action == 'set_node_pool_size':
                return self._set_node_pool_size(
                    command.get('location'),
                    command.get('cluster_name'),
                    command.get('node_pool_name'),
                    command.get('node_count')
                )
            elif action == 'get_cluster_status':
                return self._get_cluster_status(command.get('location'), command.get('cluster_name'))
            elif action == 'get_pod_details':
                return self._get_pod_details(command.get('location'), command.get('cluster_name'), command.get('namespace'), command.get('pod_name'))
            elif action == 'get_pod_logs':
                return self._get_pod_logs(command.get('location'), command.get('cluster_name'), command.get('namespace'), command.get('pod_name'))
            elif action == 'get_recent_events':
                return self._get_recent_events(command.get('location'), command.get('cluster_name'), command.get('namespace'))
            elif action == 'find_pod_namespace':
                return self._find_pod_namespace(command.get('location'), command.get('cluster_name'), command.get('pod_name'))
            elif action == 'delete_pod':
                return self._delete_pod(command.get('location'), command.get('cluster_name'), command.get('namespace'), command.get('pod_name'))
            elif action == 'restart_deployment':
                return self._restart_deployment(command.get('location'), command.get('cluster_name'), command.get('namespace'), command.get('deployment_name'))
            elif action == 'scale_deployment':
                return self._scale_deployment(command.get('location'), command.get('cluster_name'), command.get('namespace'), command.get('deployment_name'), command.get('replicas'))
            elif action == 'list_deployments':
                return self._list_deployments(command.get('location'), command.get('cluster_name'), command.get('namespace'))
            else:
                return {'status': 'ERROR', 'message': f"Unknown action: {action}"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _get_cluster_info(self, location: str, cluster_name: str) -> Dict:
        """Get GKE cluster information"""
        try:
            cluster_path = f"projects/{self.project_id}/locations/{location}/clusters/{cluster_name}"
            request = container_v1.GetClusterRequest(name=cluster_path)
            cluster = self.cluster_manager_client.get_cluster(request=request)
            
            return {
                'status': 'SUCCESS',
                'cluster_info': {
                    'name': cluster.name,
                    'status': str(cluster.status.name),
                    'location': location,
                    'node_count': cluster.current_node_count
                }
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _get_node_pools(self, location: str, cluster_name: str) -> Dict:
        """Get node pools information"""
        try:
            cluster_path = f"projects/{self.project_id}/locations/{location}/clusters/{cluster_name}"
            request = container_v1.GetClusterRequest(name=cluster_path)
            cluster = self.cluster_manager_client.get_cluster(request=request)
            
            node_pools = []
            for pool in cluster.node_pools:
                node_pools.append({
                    'name': pool.name,
                    'status': pool.status.name,
                    'initial_node_count': pool.initial_node_count
                })
            
            return {'status': 'SUCCESS', 'node_pools': node_pools}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _set_node_pool_size(self, location: str, cluster_name: str, node_pool_name: str, node_count: int) -> Dict:
        """Set node pool size"""
        try:
            node_pool_path = (
                f"projects/{self.project_id}/locations/{location}/"
                f"clusters/{cluster_name}/nodePools/{node_pool_name}"
            )
            request = container_v1.SetNodePoolSizeRequest(
                name=node_pool_path, node_count=node_count
            )
            operation = self.cluster_manager_client.set_node_pool_size(request=request)
            return {
                'status': 'SUCCESS',
                'message': f"Node pool {node_pool_name} resized to {node_count}"
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _get_cluster_status(self, location: str, cluster_name: str) -> Dict:
        """Get cluster status"""
        try:
            cluster_path = f"projects/{self.project_id}/locations/{location}/clusters/{cluster_name}"
            request = container_v1.GetClusterRequest(name=cluster_path)
            cluster = self.cluster_manager_client.get_cluster(request=request)
            
            return {
                'status': 'SUCCESS',
                'cluster_status': {
                    'status': cluster.status.name,
                    'node_count': cluster.current_node_count
                }
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _ensure_credentials(self, location: str, cluster_name: str) -> bool:
        """Get GKE credentials for kubectl"""
        try:
            cmd = [
                "gcloud", "container", "clusters", "get-credentials",
                cluster_name,
                f"--location={location}",
                f"--project={self.project_id}"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to get credentials: {e.stderr.decode()}")

    def _run_kubectl(self, args: list) -> Dict:
        """Run a kubectl command"""
        try:
            cmd = ["kubectl"] + args
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return {'status': 'FAILURE', 'error': result.stderr.strip()}
            
            return {'status': 'SUCCESS', 'output': result.stdout.strip()}
        except subprocess.TimeoutExpired:
            return {'status': 'ERROR', 'message': "kubectl command timed out"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _get_pod_details(self, location: str, cluster: str, namespace: str, pod: str) -> Dict:
        """Get detailed pod description"""
        try:
            self._ensure_credentials(location, cluster)
            return self._run_kubectl(["describe", "pod", pod, "-n", namespace])
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _get_pod_logs(self, location: str, cluster: str, namespace: str, pod: str) -> Dict:
        """Get pod logs"""
        try:
            self._ensure_credentials(location, cluster)
            # customized to get last 50 lines
            return self._run_kubectl(["logs", pod, "-n", namespace, "--tail=50"])
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _get_recent_events(self, location: str, cluster: str, namespace: str) -> Dict:
        """Get events in namespace"""
        try:
            self._ensure_credentials(location, cluster)
            # Sort by timestamp to get recent ones
            return self._run_kubectl(["get", "events", "-n", namespace, "--sort-by=.metadata.creationTimestamp"])
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _find_pod_namespace(self, location: str, cluster: str, pod_name: str) -> Dict:
        """Find which namespace a pod belongs to"""
        try:
            self._ensure_credentials(location, cluster)
            # Search all namespaces
            result = self._run_kubectl(["get", "pods", "--all-namespaces", "-o", "json"])
            
            if result['status'] != 'SUCCESS':
                return result
                
            try:
                data = json.loads(result['output'])
                items = data.get('items', [])
                found = []
                
                for item in items:
                    name = item['metadata']['name']
                    if pod_name in name: # substring match to be helpful
                        found.append({
                            'name': name,
                            'namespace': item['metadata']['namespace'],
                            'status': item['status']['phase']
                        })
                
                if not found:
                    return {'status': 'FAILURE', 'message': f"Pod {pod_name} not found in any namespace"}
                
                return {'status': 'SUCCESS', 'candidates': found}
                
            except json.JSONDecodeError:
                return {'status': 'ERROR', 'message': "Failed to parse kubectl output"}
                
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _delete_pod(self, location: str, cluster: str, namespace: str, pod: str) -> Dict:
        """Delete a pod to force restart"""
        try:
             self._ensure_credentials(location, cluster)
             return self._run_kubectl(["delete", "pod", pod, "-n", namespace])
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _restart_deployment(self, location: str, cluster: str, namespace: str, deployment: str) -> Dict:
        """Restart a deployment by doing rollout restart"""
        try:
            self._ensure_credentials(location, cluster)
            result = self._run_kubectl(["rollout", "restart", "deployment", deployment, "-n", namespace])
            if result['status'] == 'SUCCESS':
                return {
                    'status': 'SUCCESS',
                    'message': f"Deployment {deployment} restarted successfully",
                    'output': result.get('output', '')
                }
            return result
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _scale_deployment(self, location: str, cluster: str, namespace: str, deployment: str, replicas: int) -> Dict:
        """Scale a deployment to specified replicas"""
        try:
            self._ensure_credentials(location, cluster)
            result = self._run_kubectl(["scale", "deployment", deployment, f"--replicas={replicas}", "-n", namespace])
            if result['status'] == 'SUCCESS':
                return {
                    'status': 'SUCCESS',
                    'message': f"Deployment {deployment} scaled to {replicas} replicas",
                    'output': result.get('output', '')
                }
            return result
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _list_deployments(self, location: str, cluster: str, namespace: str) -> Dict:
        """List all deployments in a namespace"""
        try:
            self._ensure_credentials(location, cluster)
            namespace_arg = namespace or "default"
            result = self._run_kubectl(["get", "deployments", "-n", namespace_arg, "-o", "json"])
            
            if result['status'] != 'SUCCESS':
                return result
            
            try:
                data = json.loads(result['output'])
                deployments = []
                for item in data.get('items', []):
                    deployments.append({
                        'name': item['metadata']['name'],
                        'replicas': item['spec'].get('replicas', 0),
                        'ready': item['status'].get('readyReplicas', 0),
                        'available': item['status'].get('availableReplicas', 0)
                    })
                return {'status': 'SUCCESS', 'deployments': deployments}
            except json.JSONDecodeError:
                return {'status': 'ERROR', 'message': "Failed to parse kubectl output"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

