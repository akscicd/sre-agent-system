"""
GCP Agent - Unified Cloud Platform Agent
Handles all GCP resources: GCE (VMs), GKE (Kubernetes), GCS (Storage).
Combines former gcp_platform_specialist and cloud_specialist.
"""

from google import genai
from google.genai import types
from tools.gce_executor import GCEExecutorTool
from tools.gke_executor import GKEExecutorTool
from tools.gcs_executor import GCSExecutorTool
import yaml
import json
import time
import subprocess

def load_config():
    with open('adk.yaml', 'r') as f:
        return yaml.safe_load(f)

class GCPAgent:
    """
    Unified GCP Agent for all cloud platform operations.
    Handles: GCE (VMs, Firewall, Disks), GKE (Pods, Deployments), GCS (Buckets).
    """
    
    def __init__(self, project_id: str):
        self.project_id = project_id  # Incident's project for operations
        self.config = load_config()
        
        # Use the configuration project for Vertex AI where the service is enabled.
        vertex_project = self.config['gcp']['project_id']
        self.client = genai.Client(
            vertexai=True, 
            project=vertex_project, 
            location=self.config['gcp']['region']
        )
        
        # Initialize executors with INCIDENT project
        dry_run = self.config['execution']['dry_run']
        self.gce_executor = GCEExecutorTool(project_id, dry_run)
        self.gke_executor = GKEExecutorTool(project_id, dry_run)
        self.gcs_executor = GCSExecutorTool(project_id, dry_run)
        
        self.model_name = self.config['models']['default']

    def troubleshoot(self, incident_description: str, context: dict, history: list = None) -> dict:
        """
        Main entry point - routes to appropriate handler based on resource type.
        """
        resource_type = context.get('resource_type', 'GCE')
        
        if resource_type in ['GKE', 'POD', 'DEPLOYMENT', 'KUBERNETES']:
            return self._handle_gke(incident_description, context, history)
        elif resource_type in ['GCS', 'BUCKET', 'STORAGE']:
            return self._handle_gcs(incident_description, context, history)
        else:
            # Default: GCE (VMs, Firewall, etc.)
            return self._handle_gce(incident_description, context, history)

    def _handle_gce(self, incident: str, context: dict, history: list) -> dict:
        """Handle GCE VM and infrastructure issues."""
        
        vm_name = context.get('resource_name', '')
        zone = context.get('zone', '')
        
        print(f"GCP Agent: Checking VM '{vm_name}' in zone '{zone}'")
        
        final_output = {
            "status": "INVESTIGATING",
            "findings": [],
            "actions_taken": []
        }
        
        if not vm_name or not zone:
            final_output['findings'].append("Missing VM name or zone in context")
            final_output['status'] = 'NEEDS_HANDOFF'
            final_output['suggested_specialist'] = 'linux_agent'
            return final_output
        
        try:
            # Step 1: Get VM status
            status_result = self.gce_executor.execute_command({
                'action': 'get_instance_info',
                'instance_name': vm_name,
                'zone': zone
            })
            
            if status_result.get('status') != 'SUCCESS':
                final_output['findings'].append(f"Could not get VM status: {status_result.get('message')}")
                final_output['status'] = 'NEEDS_HANDOFF'
                return final_output
            
            instance_status = status_result.get('instance_status', 'UNKNOWN')
            final_output['findings'].append(f"VM Status: {instance_status}")
            
            # Step 2: Handle STOPPED/TERMINATED VMs
            # ReAct Pattern: Start VM, then return to allow re-discovery of updated state
            if instance_status in ['TERMINATED', 'STOPPED']:
                final_output['findings'].append(f"CRITICAL: VM is {instance_status}!")
                
                start_result = self.gce_executor.execute_command({
                    'action': 'start_instance',
                    'instance_name': vm_name,
                    'zone': zone
                })
                
                if start_result.get('status') == 'SUCCESS':
                    final_output['actions_taken'].append(f"Started VM {vm_name}")
                    final_output['findings'].append("VM has been started. Need to re-check state after boot.")
                    
                    # ReAct: Return after action to allow observation (re-discovery)
                    # The incident_manager should call discovery_agent to get fresh state
                    final_output['status'] = 'NEEDS_HANDOFF'
                    final_output['solution'] = f"Started VM {vm_name}. Please re-discover to check external IP and continue diagnosis."
                    final_output['suggested_specialist'] = 'discovery_agent'
                    return final_output
                else:
                    final_output['findings'].append(f"Failed to start VM: {start_result.get('message')}")
                    final_output['status'] = 'UNRESOLVED'
                    return final_output
            


            # Step 3: VM is RUNNING - check external IP
            if instance_status == 'RUNNING':
                external_ip = context.get('external_ip')
                
                if not external_ip or external_ip == 'None' or external_ip.strip() == '':
                    # No external IP - try to assign one
                    final_output['findings'].append("VM is RUNNING but has NO EXTERNAL IP")
                    
                    ip_result = self.gce_executor.execute_command({
                        'action': 'add_external_ip',
                        'instance_name': vm_name,
                        'zone': zone
                    })
                    
                    if ip_result.get('status') == 'SUCCESS':
                        new_ip = ip_result.get('external_ip', 'assigned')
                        final_output['actions_taken'].append(f"Assigned external IP: {new_ip}")
                        final_output['status'] = 'RESOLVED'
                        final_output['solution'] = f"Assigned external IP {new_ip} to VM"
                        return final_output
                    else:
                        final_output['findings'].append(f"Failed to assign IP: {ip_result.get('message')}")
                        final_output['status'] = 'UNRESOLVED'
                        return final_output
                
                # Has external IP - check firewall rules
                final_output['findings'].append(f"VM is RUNNING with external IP: {external_ip}")
                
                fw_result = self.gce_executor.execute_command({
                    'action': 'check_firewall_rules',
                    'instance_name': vm_name,
                    'zone': zone
                })
                
                if fw_result.get('status') == 'SUCCESS':
                    http_allowed = fw_result.get('http_allowed', False)
                    https_allowed = fw_result.get('https_allowed', False)
                    ssh_allowed = fw_result.get('ssh_allowed', False)
                    network = fw_result.get('network', 'default')
                    firewall_fixed = False
                    
                    # Create missing firewall rules
                    
                    # 1. SSH Check (CRITICAL for linux_agent)
                    if not ssh_allowed:
                        final_output['findings'].append("FIREWALL BLOCKING SSH (Port 22)! SSH BLOCKED")
                        final_output['findings'].append("Attempting to create allow-ssh firewall rule...")
                        
                        create_result = self.gce_executor.execute_command({
                            'action': 'create_firewall_rule',
                            'rule_name': 'allow-ssh',
                            'ports': ['22'],
                            'network': network
                        })
                        
                        if create_result.get('status') == 'SUCCESS':
                            final_output['actions_taken'].append("Created firewall rule: allow-ssh")
                            final_output['findings'].append(f"SUCCESS: {create_result.get('message')}")
                            firewall_fixed = True
                        else:
                            final_output['findings'].append(f"Failed to create SSH rule: {create_result.get('message')}")
                            
                    # 2. HTTP Check
                    if not http_allowed:
                        final_output['findings'].append("FIREWALL BLOCKING HTTP! HTTP: BLOCKED, HTTPS: " + ("allowed" if https_allowed else "BLOCKED"))
                        final_output['findings'].append("Attempting to create allow-http firewall rule...")
                        
                        create_result = self.gce_executor.execute_command({
                            'action': 'create_firewall_rule',
                            'rule_name': 'allow-http',
                            'ports': ['80'],
                            'network': network
                        })
                        
                        if create_result.get('status') == 'SUCCESS':
                            final_output['actions_taken'].append("Created firewall rule: allow-http")
                            final_output['findings'].append(f"SUCCESS: {create_result.get('message')}")
                            firewall_fixed = True
                        else:
                            final_output['findings'].append(f"Failed to create HTTP rule: {create_result.get('message')}")
                    
                    # 3. HTTPS Check
                    if not https_allowed:
                        final_output['findings'].append("FIREWALL BLOCKING HTTPS!")
                        final_output['findings'].append("Attempting to create allow-https firewall rule...")
                        
                        create_result = self.gce_executor.execute_command({
                            'action': 'create_firewall_rule',
                            'rule_name': 'allow-https',
                            'ports': ['443'],
                            'network': network
                        })
                        
                        if create_result.get('status') == 'SUCCESS':
                            final_output['actions_taken'].append("Created firewall rule: allow-https")
                            final_output['findings'].append(f"SUCCESS: {create_result.get('message')}")
                            firewall_fixed = True
                        else:
                            final_output['findings'].append(f"Failed to create HTTPS rule: {create_result.get('message')}")
                    
                    if firewall_fixed:
                        final_output['status'] = 'RESOLVED'
                        final_output['solution'] = 'Created firewall rules to allow access (SSH/HTTP/HTTPS)'
                        # ReAct: Recommend handing off to linux_agent to try SSH again immediately
                        final_output['suggested_specialist'] = 'linux_agent'
                        return final_output
                    
                    # Both allowed - do health check
                    if http_allowed and https_allowed:
                        final_output['findings'].append(f"Firewall rules OK: HTTP: allowed, HTTPS: allowed")
                        final_output['findings'].append(f"Performing HTTP health check on {external_ip}...")
                        
                        try:
                            result = subprocess.run(
                                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '-m', '10', f'http://{external_ip}'],
                                capture_output=True, text=True, timeout=15
                            )
                            http_code = result.stdout.strip()
                            
                            if http_code and http_code.startswith(('2', '3')):
                                final_output['findings'].append(f"HTTP health check PASSED! Status code: {http_code}")
                                final_output['findings'].append("Web server is accessible from external network!")
                                final_output['status'] = 'RESOLVED'
                                final_output['solution'] = f"Web server is accessible at http://{external_ip} (HTTP {http_code}). The reported incident may have been temporary or has already been resolved."
                                return final_output
                            else:
                                final_output['findings'].append(f"HTTP health check returned: {http_code}")
                        except Exception as e:
                            final_output['findings'].append(f"HTTP health check failed: {str(e)}")
                else:
                    final_output['findings'].append(f"Could not check firewall: {fw_result.get('message')}")
                
                # If we get here, issue is likely at OS/application level
                final_output['findings'].append("Issue is likely at OS/application level.")
                final_output['suggested_specialist'] = 'linux_agent'
                final_output['status'] = 'NEEDS_HANDOFF'
                return final_output
        
        except Exception as e:
            final_output['findings'].append(f"Error: {str(e)}")
            final_output['status'] = 'ERROR'
        
        return final_output

    def handle_disk_resize(self, zone: str, disk_name: str, new_size_gb: int) -> dict:
        """
        Handle disk resize requests from other agents (e.g., linux_agent).
        
        Args:
            zone: GCP zone of the disk
            disk_name: Name of the disk to resize
            new_size_gb: New size in GB
            
        Returns:
            Result dictionary with status and details
        """
        final_output = {
            "status": "INVESTIGATING",
            "findings": [],
            "actions_taken": []
        }
        
        # Step 1: Get current disk info
        disk_info = self.gce_executor.execute_command({
            'action': 'get_disk_info',
            'zone': zone,
            'disk_name': disk_name
        })
        
        if disk_info.get('status') != 'SUCCESS':
            final_output['findings'].append(f"Could not get disk info: {disk_info.get('message')}")
            final_output['status'] = 'ERROR'
            return final_output
        
        current_size = disk_info['disk_info']['size_gb']
        final_output['findings'].append(f"Current disk size: {current_size}GB")
        
        if new_size_gb <= current_size:
            final_output['findings'].append(f"Requested size ({new_size_gb}GB) is not larger than current ({current_size}GB)")
            final_output['status'] = 'ERROR'
            final_output['solution'] = "Disks can only be expanded, not shrunk."
            return final_output
        
        # Step 2: Resize the disk
        final_output['findings'].append(f"Resizing disk from {current_size}GB to {new_size_gb}GB...")
        
        resize_result = self.gce_executor.execute_command({
            'action': 'resize_disk',
            'zone': zone,
            'disk_name': disk_name,
            'new_size_gb': new_size_gb
        })
        
        if resize_result.get('status') == 'SUCCESS':
            final_output['actions_taken'].append(f"Resized disk {disk_name} from {current_size}GB to {new_size_gb}GB")
            final_output['status'] = 'RESOLVED'
            final_output['solution'] = (
                f"Disk {disk_name} resized from {current_size}GB to {new_size_gb}GB. "
                f"Note: Run 'sudo resize2fs /dev/sda1' or 'sudo xfs_growfs /' inside the VM to expand the filesystem."
            )
            return final_output
        else:
            final_output['findings'].append(f"Failed to resize disk: {resize_result.get('message')}")
            final_output['status'] = 'ERROR'
            return final_output


    def _handle_gke(self, incident: str, context: dict, history: list) -> dict:
        """Handle GKE/Kubernetes issues."""
        
        system_instruction = """You are a GKE/Kubernetes Specialist.
Your goal is to diagnose and fix Kubernetes issues.

**Pod Capabilities:**
- get_pod_details: Describe a pod's configuration and status
- get_pod_logs: Get pod logs for debugging
- find_pod_namespace: Find which namespace a pod is in
- delete_pod: Delete a pod to force restart
- get_recent_events: Get events in a namespace

**Deployment Capabilities:**
- list_deployments: List all deployments in a namespace
- restart_deployment: Restart a deployment (rollout restart)
- scale_deployment: Scale a deployment to N replicas

**Common Issues:**
- CrashLoopBackOff: Check logs for crash reason, then delete_pod
- ImagePullBackOff: Check image name and registry permissions
- Pending: Check resource requests vs available capacity (describe pod events)
- OOMKilled: Check memory limits
- Deployment scaled to 0: Use scale_deployment to restore replicas

**Workflow:**
1. Find the pod (get_pod_details or find_pod_namespace)
2. Check events and status
3. Get logs if container is crashing
4. Fix: delete_pod to restart individual pod, or restart_deployment for deployment issues
5. If deployment scaled to 0, use scale_deployment to restore replicas
"""
        
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="manage_gke",
                        description="Manage GKE Kubernetes resources (pods and deployments)",
                        parameters={
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["get_pod_details", "get_pod_logs", "find_pod_namespace", "delete_pod", "get_recent_events", "list_deployments", "restart_deployment", "scale_deployment"],
                                    "description": "Action to perform"
                                },
                                "pod_name": {"type": "string", "description": "Name of the pod"},
                                "deployment_name": {"type": "string", "description": "Name of the deployment"},
                                "namespace": {"type": "string", "description": "Kubernetes namespace (default: 'default')"},
                                "cluster_name": {"type": "string", "description": "GKE cluster name"},
                                "location": {"type": "string", "description": "Cluster location/region"},
                                "replicas": {"type": "integer", "description": "Number of replicas for scale_deployment"}
                            },
                            "required": ["action"]
                        }
                    )
                ]
            )
        ]

        
        chat = self.client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.1
            )
        )
        
        prompt = f"""
Incident: {incident}
Context: {json.dumps(context)}
History: {history}

Please investigate the Kubernetes issue.
"""
        
        return self._run_agent_loop(chat, prompt, 'gke')

    def _handle_gcs(self, incident: str, context: dict, history: list) -> dict:
        """Handle GCS/Storage issues."""
        
        system_instruction = """You are a GCS Storage Specialist.
Your goal is to diagnose and fix Cloud Storage issues.

**Capabilities:**
- get_bucket_metadata: Check bucket configuration
- get_bucket_iam: Check IAM permissions
- list_bucket_contents: List objects in bucket

**Common Issues:**
- 403 Forbidden: Check IAM permissions
- Missing objects: Check lifecycle rules
- Public access issues: Check public access prevention

**Workflow:**
1. Check bucket metadata and IAM
2. List contents if needed
3. Report findings
"""
        
        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="manage_gcs",
                        description="Manage GCS bucket and objects",
                        parameters={
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["get_bucket_metadata", "get_bucket_iam", "list_bucket_contents"],
                                    "description": "Action to perform"
                                },
                                "bucket_name": {"type": "string", "description": "Name of the GCS bucket"},
                                "prefix": {"type": "string", "description": "Object prefix filter (optional)"}
                            },
                            "required": ["action", "bucket_name"]
                        }
                    )
                ]
            )
        ]
        
        chat = self.client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.1
            )
        )
        
        prompt = f"""
Incident: {incident}
Context: {json.dumps(context)}

Please investigate the GCS storage issue.
"""
        
        return self._run_agent_loop(chat, prompt, 'gcs')

    def _run_agent_loop(self, chat, prompt: str, executor_type: str) -> dict:
        """Run the agent conversation loop."""
        
        actions_taken = []
        findings = []
        is_resolved = False
        
        response = self._safe_send(chat, prompt)
        max_steps = 5
        step = 0
        
        while response and step < max_steps:
            step += 1
            part = response.candidates[0].content.parts[0]
            
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                name = fc.name
                args = dict(fc.args)
                
                tool_output = "Error: Unknown tool"
                
                if name == "manage_gke":
                    action = args.get('action')
                    target = args.get('pod_name') or args.get('deployment_name') or 'N/A'
                    actions_taken.append(f"GKE: {action} on {target}")
                    
                    cmd = {
                        'action': action,
                        'namespace': args.get('namespace', 'default'),
                        'pod_name': args.get('pod_name'),
                        'deployment_name': args.get('deployment_name'),
                        'replicas': args.get('replicas'),
                        'cluster_name': args.get('cluster_name'),
                        'location': args.get('location', self.config['gcp']['region'])
                    }
                    res = self.gke_executor.execute_command(cmd)
                    tool_output = json.dumps(res)
                    findings.append(f"GKE {action}: {res.get('status')}")

                
                elif name == "manage_gcs":
                    action = args.get('action')
                    bucket = args.get('bucket_name')
                    actions_taken.append(f"GCS: {action} on {bucket}")
                    
                    cmd = {'action': action, 'bucket_name': bucket, 'prefix': args.get('prefix')}
                    res = self.gcs_executor.execute_command(cmd)
                    tool_output = json.dumps(res)
                    findings.append(f"GCS {action}: {res.get('status')}")
                
                response = self._safe_send(chat, types.Part(
                    function_response=types.FunctionResponse(
                        name=name,
                        response={"result": tool_output}
                    )
                ))
            else:
                findings.append(response.text)
                if "RESOLVED" in response.text or "fixed" in response.text.lower():
                    is_resolved = True
                break
        
        return {
            "status": "RESOLVED" if is_resolved else "NEEDS_HANDOFF",
            "findings": findings,
            "actions_taken": actions_taken,
            "solution": response.text if is_resolved and response else None,
            "suggested_specialist": "linux_agent"
        }

    def _safe_send(self, chat, content):
        """Send message with retry logic for 429 errors."""
        retries = 3
        backoff = 10
        while retries > 0:
            try:
                time.sleep(2)
                return chat.send_message(content)
            except Exception as e:
                if "429" in str(e) or "Resource exhausted" in str(e):
                    print(f"429 Hit. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                    retries -= 1
                else:
                    raise e
        return None


# Standalone function for simple import
def gcp_agent(incident, context, history):
    """Entry point for GCP Agent."""
    agent = GCPAgent(context.get('project_id'))
    return agent.troubleshoot(incident, context, history)
