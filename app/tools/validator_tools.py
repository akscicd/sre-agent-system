"""
Validator Tools - Verification utilities for the Validator Agent
"""

import urllib.request
import urllib.error
from typing import Dict, Any
from tools.gce_executor import GCEExecutorTool
from tools.gke_executor import GKEExecutorTool

class ValidatorTools:
    """Tools for independent validation of fixes"""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.gce_tool = GCEExecutorTool(project_id, dry_run=False) # Read-only checks are safe
        self.gke_tool = GKEExecutorTool(project_id, dry_run=False)
        
    def check_endpoint_health(self, url: str, timeout: int = 10, expected_content: str = None) -> Dict[str, Any]:
        """Check if an HTTP endpoint is reachable and healthy"""
        try:
            # Ensure scheme
            if not url.startswith(('http://', 'https://')):
                url = f"http://{url}"
                
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'SRE-Validator-Agent'}
            )
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                content = response.read().decode('utf-8', errors='ignore')
                
                if 200 <= status_code < 300:
                    if expected_content and expected_content not in content:
                        return {
                            'status': 'FAILURE',
                            'code': status_code,
                            'message': f"Endpoint returned {status_code} but content missing '{expected_content}'"
                        }
                        
                    return {
                        'status': 'SUCCESS', 
                        'code': status_code,
                        'message': f"Endpoint {url} returned {status_code}" + (f" and contained '{expected_content}'" if expected_content else "")
                    }
                else:
                    return {
                        'status': 'FAILURE', 
                        'code': status_code,
                        'message': f"Endpoint {url} returned non-success code {status_code}"
                    }
                    
        except urllib.error.HTTPError as e:
            return {
                'status': 'FAILURE',
                'code': e.code,
                'message': f"Endpoint {url} returned {e.code}: {e.reason}"
            }
        except urllib.error.URLError as e:
            return {
                'status': 'FAILURE',
                'error': str(e.reason),
                'message': f"Failed to reach {url}"
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def verify_internal_endpoint(self, zone: str, instance: str, port: int = 80, path: str = "/") -> Dict[str, Any]:
        """Verify an internal endpoint by running curl LOCALLY on the VM via SSH"""
        curl_cmd = f"curl -I http://localhost:{port}{path} --max-time 5"
        
        result = self.gce_tool.execute_command({
            'action': 'execute_ssh_command',
            'zone': zone,
            'instance_name': instance,
            'ssh_command': curl_cmd
        })
        
        if result.get('status') == 'SUCCESS':
            output = result.get('output', '')
            if "200 OK" in output or "301 Moved" in output:
                return {'status': 'SUCCESS', 'message': f"Internal check passed: {output.splitlines()[0]}"}
            else:
                 return {'status': 'FAILURE', 'message': f"Internal check returned non-200: {output}"}
        else:
             return {'status': 'ERROR', 'message': f"SSH connection for internal check failed: {result.get('message')}"}

    def verify_gce_state(self, zone: str, instance: str, expected_status: str) -> Dict[str, Any]:
        """Verify that a GCE instance is in the expected status (e.g., RUNNING)"""
        result = self.gce_tool.execute_command({
            'action': 'get_instance_info',
            'zone': zone,
            'instance_name': instance
        })
        
        if result.get('status') != 'SUCCESS':
            return {'status': 'ERROR', 'message': f"Could not get instance info: {result.get('message')}"}
            
        current_status = result['instance_info']['status']
        
        if current_status == expected_status.upper():
            return {
                'status': 'MATCH',
                'current_status': current_status,
                'message': f"Instance {instance} is {current_status}"
            }
        else:
            return {
                'status': 'MISMATCH',
                'current_status': current_status,
                'expected_status': expected_status,
                'message': f"Instance {instance} is {current_status}, expected {expected_status}"
            }

    def verify_gke_pod_status(self, location: str, cluster: str, namespace: str, pod_name: str, expected_phase: str) -> Dict[str, Any]:
        """Verify that a GKE pod is in the expected phase (e.g., Running)"""
        # First, find the pod if namespace is ambiguous, but here we expect specific targeting
        result = self.gke_tool.execute_command({
            'action': 'get_pod_details',
            'location': location,
            'cluster_name': cluster,
            'namespace': namespace,
            'pod_name': pod_name
        })
        
        if result.get('status') != 'SUCCESS':
             return {'status': 'ERROR', 'message': f"Could not get pod details: {result.get('message')}"}
        
        output = result.get('output', '')
        
        # Kubernetes 'describe' output is text. Parsing "Status: Running"
        import re
        match = re.search(r'^Status:\s+(\w+)', output, re.MULTILINE)
        if match:
            current_phase = match.group(1)
            if current_phase.lower() == expected_phase.lower():
                return {
                    'status': 'MATCH',
                    'current_phase': current_phase,
                    'message': f"Pod {pod_name} is {current_phase}"
                }
            else:
                return {
                    'status': 'MISMATCH',
                    'current_phase': current_phase,
                    'expected_phase': expected_phase,
                    'message': f"Pod {pod_name} is {current_phase}, expected {expected_phase}"
                }
        
        return {'status': 'INCONCLUSIVE', 'message': "Could not parse Status from kubectl describe output"}

    def check_quota(self, region: str, resource_type: str) -> Dict[str, Any]:
        """Check if we have quota for a resource (Mocked for Demo)"""
        # Real impl would use ServiceUsage API or Compute quota API
        return {
            "status": "SUCCESS",
            "quota_status": "OK",
            "details": f"Quota for {resource_type} in {region}: 10/100 used.",
            "message": f"Quota check passed for {resource_type}."
        }

    def estimate_cost(self, action: str, resource_details: str) -> Dict[str, Any]:
        """Estimate cost impact of an action (Mocked for Demo)"""
        # Simple heuristic cost table
        cost_map = {
            "n1-standard-1": "$24.27/mo",
            "n1-standard-2": "$48.54/mo",
            "e2-medium": "$25.00/mo"
        }
        
        cost = "$0.00"
        for k, v in cost_map.items():
            if k in resource_details:
                cost = v
                break
                
        return {
            "status": "SUCCESS", 
            "estimated_cost": cost,
            "message": f"Action '{action}' estimated cost: {cost}. Within budget."
        }
