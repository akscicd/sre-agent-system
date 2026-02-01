"""
Discovery Agent - Read-Only Scout
Gathers context about resources before routing incidents.
"""

try:
    from google.cloud import logging_v2
    from google.cloud import compute_v1
    from google.cloud import container_v1
    from google.cloud import asset_v1
    from google.cloud import resourcemanager_v3
except ImportError:
    logging_v2 = None
    compute_v1 = None
    container_v1 = None
    asset_v1 = None
    resourcemanager_v3 = None
    print("Warning: Google Cloud libraries not fully installed. Discovery Agent will be limited.")

import time
from datetime import datetime, timedelta

class DiscoveryAgent:
    def __init__(self, project_id: str):
        self.project_id = project_id  # Default project for fallback only
        # Initialize clients lazily or catch errors for demo safety
        self.logging_client = None
        if logging_v2:
            try:
                self.logging_client = logging_v2.LoggingServiceV2Client()
            except Exception as e:
                print(f"Warning: Could not init Logging Client: {e}")
    
    def list_accessible_projects(self) -> list:
        """
        List all GCP projects the service account has access to.
        Returns a list of project IDs.
        """
        if not resourcemanager_v3:
            print("Resource Manager library not available, using default project only")
            return [self.project_id]
        
        try:
            client = resourcemanager_v3.ProjectsClient()
            projects = []
            
            # List all projects (service account must have appropriate permissions)
            request = resourcemanager_v3.SearchProjectsRequest()
            for project in client.search_projects(request=request):
                if project.state == resourcemanager_v3.Project.State.ACTIVE:
                    projects.append(project.project_id)
            
            print(f"Found {len(projects)} accessible projects")
            return projects if projects else [self.project_id]
        except Exception as e:
            print(f"Could not list projects: {e}")
            return [self.project_id]
    
    def search_resource_in_project(self, project_id: str, resource_name: str) -> dict:
        """
        Search for a specific resource in a single project using Asset Inventory.
        """
        if not asset_v1:
            return None
        
        try:
            client = asset_v1.AssetServiceClient()
            scope = f"projects/{project_id}"
            
            request = asset_v1.SearchAllResourcesRequest(
                scope=scope,
                query=resource_name,
                asset_types=[
                    "compute.googleapis.com/Instance",
                    "container.googleapis.com/Cluster",
                    "storage.googleapis.com/Bucket"
                ],
                page_size=5
            )
            
            for result in client.search_all_resources(request=request):
                # Found it!
                r_type = "UNKNOWN"
                if "Instance" in result.asset_type:
                    r_type = "GCE"
                elif "Cluster" in result.asset_type:
                    r_type = "GKE"
                elif "Bucket" in result.asset_type:
                    r_type = "GCS"
                
                zone = "unknown"
                if result.location:
                    zone = result.location
                
                return {
                    "resource_name": result.display_name,
                    "resource_type": r_type,
                    "zone": zone,
                    "project_id": project_id
                }
            return None  # Not found in this project
        except Exception as e:
            return None
    
    def search_across_all_projects(self, resource_name: str, debug_list: list) -> dict:
        """
        Search for a resource across ALL accessible projects.
        Returns the first match found.
        """
        projects = self.list_accessible_projects()
        debug_list.append(f"Searching across {len(projects)} projects: {projects[:5]}{'...' if len(projects) > 5 else ''}")
        
        for project_id in projects:
            result = self.search_resource_in_project(project_id, resource_name)
            if result:
                debug_list.append(f"Found '{resource_name}' in project '{project_id}'")
                return result
        
        debug_list.append(f"Resource '{resource_name}' not found in any of {len(projects)} accessible projects")
        return None

    def search_asset_inventory(self, query_text: str) -> dict:
        """
        Search Cloud Asset Inventory for resources matching the query.
        Returns the first high-confidence match.
        """
        if not asset_v1:
            return {"error": "Asset/Inventory Library not imported"}

        try:
            client = asset_v1.AssetServiceClient()
            scope = f"projects/{self.project_id}"
            
            # Search for ANY resource matching the name
            # We filter for common types relevant to SRE
            request = asset_v1.SearchAllResourcesRequest(
                scope=scope,
                query=query_text,
                asset_types=[
                    "compute.googleapis.com/Instance",
                    "container.googleapis.com/Cluster",
                    "storage.googleapis.com/Bucket"
                ],
                page_size=5
            )

            response = client.search_all_resources(request=request)
            
            for result in response:
                # Map Asset Type to Internal Resource Type
                asset_type = result.asset_type
                r_type = "UNKNOWN"
                if "compute" in asset_type:
                    r_type = "GCE"
                elif "container" in asset_type:
                    r_type = "GKE"
                elif "storage" in asset_type:
                    r_type = "GCS"
                
                # Extract Zone/Location from additional_attributes or parent
                zone = "us-central1-a" # Default
                if result.location:
                    zone = result.location
                
                return {
                    "resource_name": result.display_name,
                    "resource_type": r_type,
                    "zone": zone,
                    "project_id": self.project_id
                }
            
            return {"warning": f"No assets found for query '{query_text}'"}
                
        except Exception as e:
            return {"error": str(e)}

    def discover_context(self, incident_text: str) -> dict:
        """
        Analyze incident text to find the resource and its type/OS.
        1. Extract potential names and project ID from text.
        2. If project specified: search that project only.
        3. If NO project specified: search across ALL accessible projects.
        4. Enrich with runtime details (GCE API).
        """
        import re
        
        # Check if user specified a project
        project_match = re.search(r'project[:\s]+([a-z0-9-]+)', incident_text.lower())
        user_specified_project = None
        if project_match:
            user_project = project_match.group(1)
            if len(user_project) > 5 and '-' in user_project:
                user_specified_project = user_project
        
        context = {
            "resource_name": "unknown",
            "resource_type": "UNKNOWN", 
            "os": "unknown",
            "zone": "unknown",
            "project_id": user_specified_project if user_specified_project else "SEARCHING...",
            "resource_found": False,
            "_debug": []
        }

        # Debug Info
        if not asset_v1: context['_debug'].append("Asset Lib Missing")
        if not compute_v1: context['_debug'].append("Compute Lib Missing")
        if user_specified_project:
            context['_debug'].append(f"Using user-specified project: {user_specified_project}")
        else:
            context['_debug'].append("No project specified - will search across all accessible projects")

        # 1. Extract potential resource names from incident text
        # Match words that look like resource names:
        # - Names with hyphens (instance-20250921-052754)
        # - Simple alphanumeric names (tempvm, webserver1)
        words = incident_text.split()
        
        # Common words to exclude
        exclude_words = {
            'web', 'server', 'the', 'not', 'accessible', 'project', 'zone', 'region',
            'instance', 'named', 'called', 'think', 'that', 'this', 'with', 'from',
            'running', 'stopped', 'terminated', 'issues', 'problem', 'error', 'help'
        }
        
        potential_names = []
        for w in words:
            clean = w.strip(".,'\"\")(:;!?")
            lower = clean.lower()
            
            # Skip common words
            if lower in exclude_words:
                continue
            
            # Skip if too short
            if len(clean) < 4:
                continue
            
            # Skip if it's the user-specified project
            if user_specified_project and clean.lower() == user_specified_project.lower():
                continue
            
            # Skip zone patterns (us-central1-a, europe-west1-b, etc.)
            if re.match(r'^[a-z]+-[a-z]+\d+-[a-z]$', lower):
                continue
            
            # Accept if it looks like a resource name:
            # 1. Has a hyphen (likely instance-name format)
            # 2. Alphanumeric with at least one letter and optionally numbers
            if '-' in clean or re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', clean):
                potential_names.append(clean)
        
        context['_debug'].append(f"Potential Names: {potential_names}")
        
        if not potential_names:
            context['_debug'].append("No resource name candidates found in incident text")
            return context
        
        # Prioritize names that look most like GCP resource names:
        # 1. Names with hyphens AND numbers (instance-20250921-052754) - highest priority
        # 2. Names with hyphens (my-vm-name)
        # 3. Simple alphanumeric names (webserver)
        def name_priority(name):
            has_hyphen = '-' in name
            has_numbers = any(c.isdigit() for c in name)
            if has_hyphen and has_numbers:
                return 0  # Highest priority - looks like auto-generated GCE name
            elif has_hyphen:
                return 1  # Medium priority - custom name with hyphens
            else:
                return 2  # Lowest priority - simple name like 'webserver'
        
        potential_names.sort(key=name_priority)
        
        candidate = potential_names[0]
        context['resource_name'] = candidate
        
        # 2. Search Strategy - depends on whether project was specified
        if user_specified_project:
            # User specified a project - search ONLY that project
            context['project_id'] = user_specified_project
            
            try:
                from tools.gce_executor import GCEExecutorTool
                executor = GCEExecutorTool(user_specified_project)
                zone_info = executor.find_instance_zone(candidate)
                
                if zone_info['status'] == 'SUCCESS':
                    context['resource_type'] = "GCE"
                    context['zone'] = zone_info['zone']
                    context['resource_found'] = True
                    context['_debug'].append(f"Found '{candidate}' in project '{user_specified_project}'")
                elif 'permission' in str(zone_info.get('message', '')).lower() or \
                     'denied' in str(zone_info.get('message', '')).lower() or \
                     'forbidden' in str(zone_info.get('message', '')).lower():
                    # Permission error - service account doesn't have access
                    context['resource_type'] = "NO_ACCESS"
                    context['_debug'].append(f"NO ACCESS: Service account does not have permission to project '{user_specified_project}'")
                    context['_debug'].append("Please ensure the service account has compute.instances.list permission in that project")
                else:
                    context['resource_type'] = "NOT_FOUND"
                    context['_debug'].append(f"'{candidate}' not found in project '{user_specified_project}'")
            except Exception as e:
                error_str = str(e).lower()
                if 'permission' in error_str or 'denied' in error_str or 'forbidden' in error_str or '403' in error_str:
                    context['resource_type'] = "NO_ACCESS"
                    context['_debug'].append(f"NO ACCESS: Service account does not have permission to project '{user_specified_project}'")
                    context['_debug'].append(f"Error: {str(e)[:100]}")
                else:
                    context['resource_type'] = "ERROR"
                    context['_debug'].append(f"Error searching project '{user_specified_project}': {str(e)[:100]}")
        else:
            # NO project specified - search across ALL accessible projects
            result = self.search_across_all_projects(candidate, context['_debug'])
            
            if result:
                context.update(result)
                context['resource_found'] = True
            else:
                # Still not found - try GCE fallback across all projects
                context['_debug'].append("Trying GCE fallback across all projects...")
                projects = self.list_accessible_projects()
                
                found = False
                for project_id in projects:
                    from tools.gce_executor import GCEExecutorTool
                    executor = GCEExecutorTool(project_id)
                    zone_info = executor.find_instance_zone(candidate)
                    if zone_info['status'] == 'SUCCESS':
                        context['resource_name'] = candidate
                        context['resource_type'] = "GCE"
                        context['zone'] = zone_info['zone']
                        context['project_id'] = project_id
                        context['resource_found'] = True
                        context['_debug'].append(f"Found '{candidate}' in project '{project_id}' via GCE fallback")
                        found = True
                        break
                
                if not found:
                    context['resource_type'] = "NOT_FOUND"
                    context['project_id'] = "UNKNOWN"
                    context['_debug'].append(f"RESOURCE NOT FOUND: '{candidate}' does not exist in any accessible project")
                    context['_debug'].append("Please specify the project ID where this resource is located")
        
        # 3. If GCE, finding status and detailed info is Critical
        if context['resource_type'] == 'GCE':
             from tools.gce_executor import GCEExecutorTool
             executor = GCEExecutorTool(context['project_id'])
             
             # Get Real-Time Info
             info = executor.execute_command({
                'action': 'get_instance_info', 
                'zone': context['zone'], 
                'instance_name': context['resource_name']
             })

             if info['status'] == 'SUCCESS':
                 # Use the new top-level fields for easy access
                 context['vm_status'] = info.get('instance_status', 'UNKNOWN')
                 # Use detailed OS (Ubuntu, RHEL, etc.) if available, fallback to detected_os
                 context['os'] = info.get('os_details') or info.get('detected_os', 'linux')
                 context['os_family'] = info.get('detected_os', 'linux')  # For routing: 'linux' or 'windows'
                 
                 # Add rich context from instance_info
                 instance_data = info.get('instance_info', {})
                 context['machine_type'] = instance_data.get('machine_type', 'unknown')
                 
                 # Network info for debugging
                 if instance_data.get('network_interfaces'):
                     nic = instance_data['network_interfaces'][0]
                     context['internal_ip'] = nic.get('internal_ip')
                     context['external_ip'] = nic.get('external_ip')
                 
                 context['_debug'].append(f"VM Status: {context['vm_status']}, OS: {context['os']}")
             else:
                 context['_debug'].append(f"Runtime Info Failed: {info.get('message')}")

        return context

    def get_discovery_report(self, incident_text: str) -> str:
        """Human readable report for the Incident Manager"""
        ctx = self.discover_context(incident_text)
        
        # Build a comprehensive report
        lines = [
            f"DISCOVERY REPORT:",
            f"- Resource: {ctx['resource_name']}",
            f"- Type: {ctx['resource_type']}",
            f"- OS: {ctx['os']}",
            f"- Zone: {ctx['zone']}",
        ]
        
        # Add GCE-specific fields if available
        if ctx.get('vm_status'):
            lines.append(f"- VM Status: {ctx['vm_status']}")
        if ctx.get('machine_type'):
            lines.append(f"- Machine Type: {ctx['machine_type']}")
        if ctx.get('internal_ip'):
            lines.append(f"- Internal IP: {ctx['internal_ip']}")
        if ctx.get('external_ip'):
            lines.append(f"- External IP: {ctx['external_ip']}")
        
        # Debug info at the end
        lines.append(f"- Debug: {ctx.get('_debug')}")
        
        return "\n".join(lines)

# Standalone tool function for the Agent
def run_discovery(incident_description: str) -> str:
    """
    Scouts the environment to identify the resource and its state.
    """
    import google.auth
    
    # Dynamic Project ID Detection (Production Ready)
    try:
        _, project_id = google.auth.default()
    except Exception as e:
        # Fallback to config if auth fails or returns no project
        import yaml
        import os
        try:
            with open('adk.yaml', 'r') as f:
                content = os.path.expandvars(f.read())
                config = yaml.safe_load(content)
            project_id = config.get('gcp', {}).get('project_id')
        except:
             return f"Error: Could not determine Project ID. Auth Error: {e}"

    if not project_id:
         return "Error: Project ID is None."

    agent = DiscoveryAgent(project_id)
    return agent.get_discovery_report(incident_description)
