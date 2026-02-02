"""
GCE Executor Tool - Executes Compute Engine commands
"""

from google.cloud import compute_v1
from typing import Dict, Any
from google.cloud import compute_v1
from typing import Dict, Any
import time
import subprocess
import re
import os

class GCEExecutorTool:
    """Tool for executing GCE troubleshooting commands"""
    
    def __init__(self, project_id: str, dry_run: bool = True):
        self.project_id = project_id
        self.dry_run = dry_run
        
        # Ensure gcloud is authenticated if using a service account file
        # This is required because gcloud CLI doesn't automatically pick up GOOGLE_APPLICATION_CREDENTIALS for command execution
        creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if creds_path and os.path.exists(creds_path):
            try:
                # Check if we are already authenticated
                check = subprocess.run(
                    ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"], 
                    capture_output=True, text=True, encoding='utf-8', errors='replace'
                )
                if not check.stdout.strip():
                    print(f"Activating service account from {creds_path}...")
                    subprocess.run(
                        ["gcloud", "auth", "activate-service-account", f"--key-file={creds_path}", "--quiet"],
                        check=True, capture_output=True
                    )
            except Exception as e:
                print(f"Warning: Failed to activate gcloud service account: {e}")

        self.instances_client = compute_v1.InstancesClient()
        
    def execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GCE command"""
        action = command.get('action')
        
        # READ-ONLY actions are always allowed, even in dry_run mode
        read_only_actions = [
            'get_instance_info', 
            'get_serial_port_output', 
            'check_guest_metrics',
            'get_instance_by_ip',
            'get_disk_info'  # Disk read operation
        ]
        
        # WRITE actions require dry_run check
        write_actions = [
            'restart_instance',
            'stop_instance', 
            'start_instance',
            'reset_instance',
            'execute_ssh_command',  # SSH can modify state
            'add_external_ip',  # Modifies network config
            'create_firewall_rule',  # Creates firewall rule
            'resize_disk'  # Disk resize operation
        ]
        
        if self.dry_run and action in write_actions:
            return {
                'status': 'DRY_RUN',
                'message': f"Would execute: {action}",
                'command': command
            }
        
        try:
            if action == 'restart_instance':
                return self._restart_instance(command.get('zone'), command.get('instance_name'))
            elif action == 'stop_instance':
                return self._stop_instance(command.get('zone'), command.get('instance_name'))
            elif action == 'start_instance':
                return self._start_instance(command.get('zone'), command.get('instance_name'))
            elif action == 'get_instance_info':
                return self._get_instance_info(command.get('zone'), command.get('instance_name'))
            elif action == 'reset_instance':
                return self._reset_instance(command.get('zone'), command.get('instance_name'))
            elif action == 'execute_ssh_command':
                return self._execute_ssh_command(command.get('zone'), command.get('instance_name'), command.get('ssh_command'))
            elif action == 'get_serial_port_output':
                return self._get_serial_port_output(command.get('zone'), command.get('instance_name'))
            elif action == 'check_guest_metrics':
                return self._check_guest_metrics(command.get('zone'), command.get('instance_name'))
            elif action == 'get_instance_by_ip':
                return self.get_instance_by_ip(command.get('ip_address'))
            elif action == 'add_external_ip':
                return self._add_external_ip(command.get('zone'), command.get('instance_name'))
            elif action == 'check_firewall_rules':
                return self._check_firewall_rules(command.get('instance_name'), command.get('zone'))
            elif action == 'create_firewall_rule':
                return self._create_firewall_rule(command.get('rule_name'), command.get('ports'), command.get('network'))
            elif action == 'get_disk_info':
                return self._get_disk_info(command.get('zone'), command.get('disk_name'))
            elif action == 'resize_disk':
                return self._resize_disk(command.get('zone'), command.get('disk_name'), command.get('new_size_gb'))
            else:
                return {'status': 'ERROR', 'message': f"Unknown action: {action}"}
        except Exception as e:
            return {'status': 'ERROR', 'message': f"Execution failed: {str(e)}"}
    
    def _restart_instance(self, zone: str, instance_name: str) -> Dict:
        """Restart a GCE instance"""
        try:
            stop_request = compute_v1.StopInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            stop_operation = self.instances_client.stop(request=stop_request)
            self._wait_for_operation(zone, stop_operation.name)
            
            start_request = compute_v1.StartInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            start_operation = self.instances_client.start(request=start_request)
            self._wait_for_operation(zone, start_operation.name)
            
            return {
                'status': 'SUCCESS',
                'message': f"Instance {instance_name} restarted successfully"
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': f"Failed to restart: {str(e)}"}
    
    def _stop_instance(self, zone: str, instance_name: str) -> Dict:
        """Stop a GCE instance"""
        try:
            request = compute_v1.StopInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            operation = self.instances_client.stop(request=request)
            self._wait_for_operation(zone, operation.name)
            return {'status': 'SUCCESS', 'message': f"Instance {instance_name} stopped"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _start_instance(self, zone: str, instance_name: str) -> Dict:
        """Start a GCE instance"""
        try:
            request = compute_v1.StartInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            operation = self.instances_client.start(request=request)
            self._wait_for_operation(zone, operation.name)
            return {'status': 'SUCCESS', 'message': f"Instance {instance_name} started"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _reset_instance(self, zone: str, instance_name: str) -> Dict:
        """Reset (hard reboot) a GCE instance"""
        try:
            request = compute_v1.ResetInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            operation = self.instances_client.reset(request=request)
            self._wait_for_operation(zone, operation.name)
            return {'status': 'SUCCESS', 'message': f"Instance {instance_name} reset"}
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    def _add_external_ip(self, zone: str, instance_name: str) -> Dict:
        """Add an ephemeral external IP to a GCE instance's primary network interface"""
        try:
            # First, get the instance to find its network interface
            get_request = compute_v1.GetInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            instance = self.instances_client.get(request=get_request)
            
            if not instance.network_interfaces:
                return {'status': 'ERROR', 'message': 'Instance has no network interfaces'}
            
            # Check if it already has an external IP
            nic = instance.network_interfaces[0]
            if nic.access_configs and len(nic.access_configs) > 0:
                existing_ip = nic.access_configs[0].nat_i_p
                if existing_ip:
                    return {
                        'status': 'SUCCESS',
                        'message': f'Instance already has external IP: {existing_ip}',
                        'external_ip': existing_ip
                    }
            
            # Create access config for ephemeral external IP
            access_config = compute_v1.AccessConfig(
                name="External NAT",
                type_="ONE_TO_ONE_NAT",
                network_tier="PREMIUM"
            )
            
            # Add the access config to the instance
            request = compute_v1.AddAccessConfigInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=instance_name,
                network_interface=nic.name or "nic0",
                access_config_resource=access_config
            )
            
            operation = self.instances_client.add_access_config(request=request)
            self._wait_for_operation(zone, operation.name)
            
            # Get the new external IP
            updated_instance = self.instances_client.get(request=get_request)
            new_ip = None
            if updated_instance.network_interfaces and updated_instance.network_interfaces[0].access_configs:
                new_ip = updated_instance.network_interfaces[0].access_configs[0].nat_i_p
            
            return {
                'status': 'SUCCESS',
                'message': f'External IP assigned successfully: {new_ip}',
                'external_ip': new_ip
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': f'Failed to add external IP: {str(e)}'}
    
    def _check_firewall_rules(self, instance_name: str, zone: str) -> Dict:
        """Check if HTTP/HTTPS firewall rules exist for an instance's network"""
        try:
            # Get the instance to find its network
            get_request = compute_v1.GetInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            instance = self.instances_client.get(request=get_request)
            
            if not instance.network_interfaces:
                return {'status': 'ERROR', 'message': 'Instance has no network interfaces'}
            
            # Get network name - usually the last part of the URL
            network_url = instance.network_interfaces[0].network
            network_name = network_url.split('/')[-1] if '/' in network_url else network_url
            
            # Get instance tags (firewall rules can target by tag)
            instance_tags = list(instance.tags.items) if instance.tags and instance.tags.items else []
            
            # List all firewall rules for the project
            firewalls_client = compute_v1.FirewallsClient()
            request = compute_v1.ListFirewallsRequest(project=self.project_id)
            firewalls = list(firewalls_client.list(request=request))
            
            ssh_allowed = False
            http_allowed = False
            https_allowed = False
            matching_rules = []
            all_rules_debug = []  # Debug info
            
            for fw in firewalls:
                # Debug: log all rules
                all_rules_debug.append(f"{fw.name}: dir={fw.direction}, src={list(fw.source_ranges) if fw.source_ranges else 'none'}")
                
                # CRITICAL FIX 1: Only check INGRESS rules
                if fw.direction and fw.direction != 'INGRESS':
                    continue
                
                # CRITICAL FIX 2: Check if rule allows traffic from external IPs (0.0.0.0/0)
                # Internal-only rules (like default-allow-internal) should NOT count
                allows_external = False
                if fw.source_ranges:
                    for src in fw.source_ranges:
                        # 0.0.0.0/0 means all IPs (including external)
                        if src == '0.0.0.0/0':
                            allows_external = True
                            break
                        # Also check for broad ranges that include external
                        # But exclude internal-only ranges like 10.0.0.0/8, 192.168.0.0/16
                        if not src.startswith(('10.', '192.168.', '172.16.', '172.17.', '172.18.', '172.19.')):
                            allows_external = True
                            break
                
                if not allows_external:
                    continue
                
                # Check if this rule applies to all instances or targets this instance
                applies = False
                if not fw.target_tags:  # Applies to all instances in network
                    applies = True
                elif instance_tags:
                    # Check if any instance tag matches firewall target tags
                    for tag in fw.target_tags:
                        if tag in instance_tags:
                            applies = True
                            break
                
                if not applies:
                    continue
                
                # Check what ports this rule allows
                for allowed in fw.allowed:
                    if allowed.I_p_protocol.lower() in ['tcp', 'all']:
                        for port in allowed.ports:
                            if port == '22' or port == 'ssh':
                                ssh_allowed = True
                                matching_rules.append(f"{fw.name} allows SSH from external")
                            if port == '80' or port == 'http':
                                http_allowed = True
                                matching_rules.append(f"{fw.name} allows HTTP from external")
                            if port == '443' or port == 'https':
                                https_allowed = True
                                matching_rules.append(f"{fw.name} allows HTTPS from external")
                            # Handle port ranges like "80-443"
                            if '-' in port:
                                try:
                                    start, end = map(int, port.split('-'))
                                    if start <= 22 <= end:
                                        ssh_allowed = True
                                        matching_rules.append(f"{fw.name} allows SSH (range)")
                                    if start <= 80 <= end:
                                        http_allowed = True
                                        matching_rules.append(f"{fw.name} allows HTTP (range)")
                                    if start <= 443 <= end:
                                        https_allowed = True
                                        matching_rules.append(f"{fw.name} allows HTTPS (range)")
                                except:
                                    pass
            
            return {
                'status': 'SUCCESS',
                'network': network_name,
                'instance_tags': instance_tags,
                'ssh_allowed': ssh_allowed,
                'http_allowed': http_allowed,
                'https_allowed': https_allowed,
                'matching_rules': matching_rules,
                'all_rules_count': len(firewalls),
                'message': f"SSH: {'allowed' if ssh_allowed else 'BLOCKED'}, HTTP: {'allowed' if http_allowed else 'BLOCKED'}, HTTPS: {'allowed' if https_allowed else 'BLOCKED'}"
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': f'Failed to check firewall rules: {str(e)}'}
    
    def _create_firewall_rule(self, rule_name: str, ports: list, network: str = 'default') -> Dict:
        """Create a firewall rule to allow specific ports"""
        try:
            firewalls_client = compute_v1.FirewallsClient()
            
            # Check if rule already exists
            try:
                existing = firewalls_client.get(project=self.project_id, firewall=rule_name)
                if existing:
                    return {
                        'status': 'SUCCESS',
                        'message': f'Firewall rule {rule_name} already exists',
                        'rule_name': rule_name
                    }
            except:
                pass  # Rule doesn't exist, proceed to create
            
            # Create the firewall rule
            firewall_rule = compute_v1.Firewall(
                name=rule_name,
                network=f"projects/{self.project_id}/global/networks/{network}",
                direction="INGRESS",
                priority=1000,
                source_ranges=["0.0.0.0/0"],  # Allow from any source
                allowed=[
                    compute_v1.Allowed(
                        I_p_protocol="tcp",
                        ports=ports
                    )
                ]
            )
            
            operation = firewalls_client.insert(
                project=self.project_id,
                firewall_resource=firewall_rule
            )
            
            # Wait for the operation to complete
            from google.cloud.compute_v1.services.global_operations import GlobalOperationsClient
            ops_client = GlobalOperationsClient()
            while True:
                result = ops_client.get(project=self.project_id, operation=operation.name)
                if result.status == compute_v1.Operation.Status.DONE:
                    break
                import time
                time.sleep(1)
            
            return {
                'status': 'SUCCESS',
                'message': f'Firewall rule {rule_name} created successfully, allowing ports: {ports}',
                'rule_name': rule_name,
                'ports': ports
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': f'Failed to create firewall rule: {str(e)}'}
    
    def _get_instance_info(self, zone: str, instance_name: str) -> Dict:
        """Get comprehensive instance information including OS detection"""
        try:
            request = compute_v1.GetInstanceRequest(
                project=self.project_id, zone=zone, instance=instance_name
            )
            instance = self.instances_client.get(request=request)
            
            # Extract disk info with licenses for OS detection
            disks = []
            detected_os = 'linux'  # Default assumption
            os_details = None  # More specific OS info
            
            for disk in instance.disks:
                disk_info = {
                    'source': disk.source,
                    'boot': disk.boot,
                    'licenses': list(disk.licenses) if disk.licenses else []
                }
                disks.append(disk_info)
                
                # OS Detection via Licenses - extract specific distro/version
                for lic in disk_info['licenses']:
                    lic_lower = lic.lower()
                    # Extract the license name (last part of URL)
                    lic_name = lic.split('/')[-1] if '/' in lic else lic
                    
                    if 'windows-cloud' in lic_lower:
                        detected_os = 'windows'
                        # Extract Windows version: windows-2022, windows-2019, windows-11, etc.
                        os_details = lic_name.replace('-', ' ').title()
                    elif 'ubuntu-os-cloud' in lic_lower or 'ubuntu' in lic_lower:
                        detected_os = 'linux'
                        os_details = f"Ubuntu ({lic_name})"
                    elif 'rhel-cloud' in lic_lower or 'rhel' in lic_lower:
                        detected_os = 'linux'
                        os_details = f"Red Hat Enterprise Linux ({lic_name})"
                    elif 'centos-cloud' in lic_lower or 'centos' in lic_lower:
                        detected_os = 'linux'
                        os_details = f"CentOS ({lic_name})"
                    elif 'debian-cloud' in lic_lower or 'debian' in lic_lower:
                        detected_os = 'linux'
                        os_details = f"Debian ({lic_name})"
                    elif 'suse-cloud' in lic_lower or 'sles' in lic_lower:
                        detected_os = 'linux'
                        os_details = f"SUSE ({lic_name})"
                    
                    if os_details:
                        break
            
            # Extract network info
            network_interfaces = []
            for nic in instance.network_interfaces:
                nic_info = {
                    'network': nic.network,
                    'subnetwork': nic.subnetwork,
                    'internal_ip': nic.network_i_p,
                    'external_ip': nic.access_configs[0].nat_i_p if nic.access_configs else None
                }
                network_interfaces.append(nic_info)
            
            return {
                'status': 'SUCCESS',
                'instance_status': str(instance.status),  # Top-level for easy access
                'detected_os': detected_os,  # Top-level: 'linux' or 'windows'
                'os_details': os_details,    # Specific distro: 'Ubuntu (ubuntu-2204-lts)'
                'instance_info': {
                    'name': instance.name,
                    'status': str(instance.status),
                    'machine_type': instance.machine_type.split('/')[-1],  # Just the type name
                    'zone': zone,
                    'os': os_details or detected_os,  # Use detailed OS if available
                    'labels': dict(instance.labels) if instance.labels else {},
                    'disks': disks,
                    'network_interfaces': network_interfaces
                }
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}
    
    
    def find_instance_zone(self, instance_name: str) -> Dict[str, Any]:
        """Find the zone of an instance by name"""
        try:
            request = compute_v1.AggregatedListInstancesRequest(
                project=self.project_id,
                filter=f"name = {instance_name}"
            )
            agg_list = self.instances_client.aggregated_list(request=request)
            
            for zone_path, response in agg_list:
                if response.instances:
                    # zone_path format: 'projects/PROJECT/zones/ZONE'
                    zone = zone_path.split('/')[-1]
                    return {
                        'status': 'SUCCESS',
                        'zone': zone,
                        'message': f"Found instance {instance_name} in {zone}"
                    }
            
            return {'status': 'ERROR', 'message': f"Instance {instance_name} not found in any zone"}
        except Exception as e:
            return {'status': 'ERROR', 'message': f"Failed to find instance: {str(e)}"}

    def _wait_for_operation(self, zone: str, operation_name: str, timeout: int = 600):
        """Wait for operation to complete"""
        operations_client = compute_v1.ZoneOperationsClient()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            request = compute_v1.GetZoneOperationRequest(
                project=self.project_id, zone=zone, operation=operation_name
            )
            # In dry run, we can't really wait for a mock without a client.
            # But the caller checks dry_run before calling this usually, OR we handle it:
            if self.dry_run:
                return

            operation = operations_client.get(request=request)
            
            if operation.status == compute_v1.Operation.Status.DONE:
                if operation.error:
                    raise Exception(f"Operation failed: {operation.error}")
                return
            time.sleep(2)
        
        raise TimeoutError(f"Operation {operation_name} timed out")

    def _execute_ssh_command(self, zone: str, instance_name: str, ssh_command: str) -> Dict:
        """Execute a command via SSH using LOCAL gcloud with retry logic"""
        # SECURITY WARNING: This executes commands as the gcloud authenticated user.
        
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                # Construct gcloud command
                cmd = [
                    "gcloud", "compute", "ssh", instance_name,
                    f"--zone={zone}",
                    f"--project={self.project_id}",
                    "--tunnel-through-iap",
                    "--quiet", 
                    "--command", ssh_command
                ]
                
                # Execute
                # We do NOT use shell=True here to avoid quoting hell. 
                # passing the list directly to subprocess.run is safer and correct for Linux/Docker environments.
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='replace')
                
                # Check if gcloud SSH ITSELF failed (VM stopped, permissions, network issues)
                # These errors appear in stderr and indicate we couldn't reach the VM at all.
                # IMPORTANT: Use SPECIFIC gcloud error patterns to avoid matching remote command output
                gcloud_errors = [
                    "Could not fetch resource",
                    "unrecognized arguments",  # Catch bad flag usage
                    "Could not SSH into",
                    "Connection timed out",
                    "Connection refused",
                    "Permission denied (publickey",  # SSH key issues
                    "instance is not running",
                    "Instance may have been terminated",
                    "Operation terminated",
                    "does not exist in zone",  # More specific
                    "Connection reset by peer",
                    "Command name argument expected"  # Catch the specific error user saw
                ]
                
                stderr_lower = result.stderr.lower()
                
                # Only check for SSH failure if:
                # 1. Return code is non-zero (command failed)
                # 2. AND there's no stdout (command didn't run at all)
                # 3. AND there's a specific gcloud error in stderr (not just 'Recommendation:')
                has_stdout = len(result.stdout.strip()) > 0
                
                # Check for actual SSH failure (not just recommendation hints or remote command failures)
                is_ssh_failure = False
                if result.returncode != 0 and not has_stdout:
                    
                    # Special check: If stderr explicitly says "exited with return code", 
                    # it means SSH connected and the remote command ran but failed.
                    # This is NOT an SSH infrastructure failure.
                    if "exited with return code" in stderr_lower:
                        is_ssh_failure = False
                    else:
                        for error_pattern in gcloud_errors:
                            if error_pattern.lower() in stderr_lower:
                                is_ssh_failure = True
                                break
                
                if is_ssh_failure:
                    if attempt < max_retries - 1:
                        print(f"SSH attempt {attempt + 1} failed (Code: {result.returncode}). Stderr: {result.stderr.strip()[:200]}")
                        # If we see the specific syntax error, don't retry, just fail fast so we don't spam logs
                        if "command name argument expected" in stderr_lower:
                             return {
                                'status': 'SSH_FAILED',
                                'return_code': result.returncode,
                                'message': f"SSH syntax error: {result.stderr.strip()}",
                                'raw_stderr': result.stderr.strip()
                            }
                        
                        print(f"Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        return {
                            'status': 'SSH_FAILED',
                            'return_code': result.returncode,
                            'message': f"SSH connection failed after {max_retries} attempts: {result.stderr.strip()[:200]}",
                            'raw_stderr': result.stderr.strip()
                        }
                
                # If we got here, SSH connected. 
                
                # AUTO-RETRY WITH SUDO LOGIC
                # If command failed (non-zero exit) and it wasn't already a sudo command,
                # retry it with sudo. This handles simplified user requests like "apt update" 
                # failing due to permissions.
                # However, don't retry if the command simply doesn't exist (exit code 127).
                if result.returncode != 0 and "sudo " not in ssh_command and result.returncode != 127:
                    # Check for "command not found" text just in case return code isn't 127
                    if "not found" not in result.stderr.lower():
                        print(f"Command '{ssh_command}' failed with code {result.returncode}. Retrying with sudo...")
                        return self._execute_ssh_command(zone, instance_name, f"sudo {ssh_command}")

                # Return SUCCESS with the remote command's exit code.
                # Non-zero exit codes from the REMOTE command (e.g., systemctl = 3) are valid status info.
                print(f"SSH Command: {ssh_command}")
                print(f"Return code: {result.returncode}")
                print(f"Stdout ({len(result.stdout)} chars): {result.stdout[:200]}")
                print(f"Stderr ({len(result.stderr)} chars): {result.stderr[:100]}")
                return {
                    'status': 'SUCCESS',
                    'return_code': result.returncode,
                    'output': result.stdout.strip(),
                    'stderr': result.stderr.strip()
                }
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    print(f"SSH timeout on attempt {attempt + 1}, retrying...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return {'status': 'ERROR', 'message': "SSH command timed out after retries"}
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"SSH error on attempt {attempt + 1}: {e}, retrying...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return {'status': 'ERROR', 'message': str(e)}
        
        return {'status': 'ERROR', 'message': 'SSH failed after all retries'}

    def _get_serial_port_output(self, zone: str, instance_name: str) -> Dict:
        """Get the serial console output of an instance"""
        try:
            request = compute_v1.GetSerialPortOutputInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=instance_name,
                port=1 # COM1 is usually the console
            )
            response = self.instances_client.get_serial_port_output(request=request)
            
            # Get last 2000 chars to avoid token limits
            content = response.contents
            last_content = content[-2000:] if len(content) > 2000 else content
            
            return {
                'status': 'SUCCESS',
                'output_tail': last_content,
                'full_size': len(content)
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _check_guest_metrics(self, zone: str, instance_name: str) -> Dict:
        """
        Placeholder for checking Guest CPU/RAM.
        In a real specific implementation, this would query api `monitoring_v3`.
        For now, we return a message explaining this requirement.
        """
        return {
            'status': 'SKIPPED',
            'message': (
                "Guest metrics (Memory/Disk) require the Ops Agent to be installed "
                "and the Monitoring API client to be configured. "
                "Please use SSH to check 'top' or 'df -h' instead."
            )
        }

    def get_instance_by_ip(self, ip_address: str) -> Dict:
        """Resolve an internal IP to an Instance Name and Zone"""
        try:
            # We must iterate zones or use aggregated list with filter
            # Filtering on networkIP might work if supported by the filter syntax
            request = compute_v1.AggregatedListInstancesRequest(
                project=self.project_id,
                # Note: 'networkInterfaces.networkIP' is the field for internal IP
                filter=f"networkInterfaces.networkIP = \"{ip_address}\""
            )
            agg_list = self.instances_client.aggregated_list(request=request)
            
            found_instances = []
            for zone_path, response in agg_list:
                if response.instances:
                    zone = zone_path.split('/')[-1]
                    for instance in response.instances:
                        found_instances.append({
                            'name': instance.name,
                            'zone': zone,
                            'status': instance.status
                        })
            
            if not found_instances:
                return {'status': 'FAILURE', 'message': f"No instance found with IP {ip_address}"}
            
            if len(found_instances) > 1:
                return {
                    'status': 'AMBIGUOUS', 
                    'message': f"Multiple instances found for IP {ip_address}",
                    'candidates': found_instances
                }
            
            return {
                'status': 'SUCCESS',
                'instance': found_instances[0],
                'message': f"Resolved {ip_address} to {found_instances[0]['name']}"
            }
            
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _get_disk_info(self, zone: str, disk_name: str) -> Dict:
        """Get disk size and status info"""
        try:
            disk_client = compute_v1.DisksClient()
            disk = disk_client.get(project=self.project_id, zone=zone, disk=disk_name)
            return {
                'status': 'SUCCESS',
                'disk_info': {
                    'name': disk.name,
                    'size_gb': disk.size_gb,
                    'status': disk.status,
                    'type': disk.type_.split('/')[-1] if disk.type_ else 'unknown',
                    'source_image': disk.source_image.split('/')[-1] if disk.source_image else None
                }
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

    def _resize_disk(self, zone: str, disk_name: str, new_size_gb: int) -> Dict:
        """Resize a persistent disk (can only increase size, not decrease)"""
        try:
            disk_client = compute_v1.DisksClient()
            
            # First, get current disk size
            current_disk = disk_client.get(project=self.project_id, zone=zone, disk=disk_name)
            current_size = current_disk.size_gb
            
            if new_size_gb <= current_size:
                return {
                    'status': 'ERROR',
                    'message': f"New size ({new_size_gb}GB) must be larger than current size ({current_size}GB). Disks can only be expanded, not shrunk."
                }
            
            # Create resize request
            resize_request = compute_v1.DisksResizeRequest(
                size_gb=new_size_gb
            )
            
            operation = disk_client.resize(
                project=self.project_id,
                zone=zone,
                disk=disk_name,
                disks_resize_request_resource=resize_request
            )
            
            # Wait for operation to complete
            self._wait_for_operation(zone, operation.name)
            
            return {
                'status': 'SUCCESS',
                'message': f"Disk {disk_name} resized from {current_size}GB to {new_size_gb}GB",
                'old_size_gb': current_size,
                'new_size_gb': new_size_gb,
                'note': 'You may need to run resize2fs or xfs_growfs inside the VM to expand the filesystem'
            }
        except Exception as e:
            return {'status': 'ERROR', 'message': str(e)}

