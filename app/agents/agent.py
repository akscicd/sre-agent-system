"""
Main Agent Entry Point for ADK - Incident Manager
This file defines the root_agent (incident_manager) that ADK loads and runs.

Architecture:
- agent.py = ADK integration layer (incident_manager + tool definitions)
- All specialist agents are called via tools for ADK UI visibility

Tools:
- discovery_agent: Scout/discover resources
- search_memory: Search past incidents
- linux_agent: Linux VM troubleshooting
- windows_agent: Windows VM troubleshooting
- gcp_agent: All GCP operations (GCE, GKE, GCS)
- validation_agent: Validate fixes
"""

from google.adk.agents import Agent
from agents.discovery_agent import DiscoveryAgent
from tools.memory_store import get_memory_store
import os
import yaml
import json
import time
import re

def load_config():
    with open('adk.yaml', 'r') as f:
        content = os.path.expandvars(f.read())
        return yaml.safe_load(content)

# Singleton instances
_discovery_agent = None
_memory_store = None
_specialists = None

def _get_discovery_agent():
    """Lazy initialization of DiscoveryAgent"""
    global _discovery_agent
    if _discovery_agent is None:
        config = load_config()
        _discovery_agent = DiscoveryAgent(config['gcp']['project_id'])
    return _discovery_agent

def _get_memory():
    """Lazy initialization of MemoryStore"""
    global _memory_store
    if _memory_store is None:
        _memory_store = get_memory_store()
    return _memory_store

def _get_specialists():
    """Lazy initialization of specialist registry"""
    global _specialists
    if _specialists is None:
        from agents.linux_agent import linux_specialist
        from agents.windows_agent import windows_specialist
        from agents.gcp_agent import gcp_agent as _gcp_agent
        
        _specialists = {
            "linux_agent": linux_specialist,
            "windows_agent": windows_specialist,
            "gcp_agent": _gcp_agent
        }
    return _specialists


def _parse_context(context_str: str) -> dict:
    """Parse context string to dict with fallback to regex for edge cases"""
    context = {}
    
    try:
        import ast
        context = ast.literal_eval(context_str)
    except Exception:
        # Fallback: extract fields using regex (handles octal-like strings)
        try:
            patterns = {
                'resource_name': r"'resource_name':\s*'([^']*)'",
                'resource_type': r"'resource_type':\s*'([^']*)'",
                'os': r"'os':\s*'([^']*)'",
                'zone': r"'zone':\s*'([^']*)'",
                'project_id': r"'project_id':\s*'([^']*)'",
                'vm_status': r"'vm_status':\s*'([^']*)'",
                'machine_type': r"'machine_type':\s*'([^']*)'",
                'internal_ip': r"'internal_ip':\s*'([^']*)'",
                'external_ip': r"'external_ip':\s*(?:'([^']*)'|None)",
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, context_str)
                if match:
                    context[key] = match.group(1) if match.group(1) else ''
            print(f"Regex parsed context - zone: {context.get('zone')}, vm: {context.get('resource_name')}")
        except Exception as e:
            print(f"Failed to parse context_str: {e}")
            context = {}
    
    return context


def _log_to_audit(specialist_name: str, incident: str, result: dict):
    """Log specialist actions to audit file"""
    try:
        log_entry = {
            "timestamp": time.time(),
            "specialist": specialist_name,
            "incident": incident,
            "result": result
        }
        with open("audit_log.json", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Audit Log Error: {e}")


def _call_specialist(specialist_name: str, incident_description: str, context: dict) -> str:
    """Internal function to call a specialist and format the result"""
    specialists = _get_specialists()
    
    if context:
        print(f"Context - zone: {context.get('zone')}, vm: {context.get('resource_name')}, project: {context.get('project_id')}, external_ip: {context.get('external_ip')}")
    
    # Get the specialist function
    specialist_fn = specialists.get(specialist_name)
    if not specialist_fn:
        return f"Unknown specialist: {specialist_name}. Available: {list(specialists.keys())}"
    
    # Call the specialist
    result = specialist_fn(incident_description, context, [])
    
    # Log to audit
    _log_to_audit(specialist_name, incident_description, result)
    
    # Format the result
    status = result.get('status', 'UNKNOWN')
    findings = result.get('findings', [])
    actions = result.get('actions_taken', [])
    
    if status == "RESOLVED":
        return f"RESOLVED\nFindings: {findings}\nActions: {actions}\nSolution: {result.get('solution')}"
    elif status == "NEEDS_HANDOFF":
        suggested = result.get('suggested_specialist', 'unknown')
        return f"UNRESOLVED - Needs handoff to {suggested}\nFindings: {findings}"
    else:
        return f"UNRESOLVED\nFindings: {findings}\nStatus: {status}"


# ===================== ADK TOOLS =====================

def discovery_agent(incident_description: str) -> str:
    """
    Discovery Agent - Scout and identify resources related to the incident.
    
    Scans GCP resources (VMs, Pods, Buckets) to understand what the incident 
    description refers to. Returns resource information including:
    - resource_name, resource_type
    - OS family, zone, project_id
    - VM status (RUNNING, TERMINATED, etc.)
    - Internal/external IPs
    
    Args:
        incident_description: A description of the incident (e.g., "web server xyz is not accessible")
        
    Returns:
        Context dictionary with resource details
    """
    agent = _get_discovery_agent()
    context = agent.discover_context(incident_description)
    return str(context)


def search_memory(incident_description: str) -> str:
    """
    Memory Search - Search for similar past incidents.
    
    Checks the memory store for previously resolved incidents that are similar
    to the current one. If a match is found, returns the past solution.
    
    Args:
        incident_description: Description of the current incident
        
    Returns:
        Past solution if found, or "No relevant past incidents found"
    """
    memory = _get_memory()
    similar = memory.search([incident_description])
    
    if similar and len(similar) > 0 and similar[0].get('confidence', 0) > 0.7:
        return f"Found similar incident: {similar[0].get('incident', 'unknown')}. Solution: {similar[0].get('solution', 'none')}"
    
    print(f"Memory Search: {len(memory.memories)} memories stored in {memory.filepath}")
    return "No relevant past incidents found."


# ===================== SPECIALIST TOOLS =====================

def linux_agent(incident_description: str, context_str: str) -> str:
    """
    Linux Agent - Diagnoses and fixes Linux VM issues.
    
    Capabilities:
    - SSH into Linux VMs and run diagnostic commands
    - Check service status (systemctl, ps)
    - Analyze logs (/var/log/*, journalctl)
    - Check disk, memory, CPU usage
    - Restart services if needed
    
    Use when:
    - VM is RUNNING and OS is Linux
    - Need to check web server (Apache, Nginx) status
    - Need to check application logs
    
    Args:
        incident_description: The issue to diagnose
        context_str: Context from discovery_agent (VM name, zone, IPs, etc.)
    """
    context = _parse_context(context_str)
    print(f"Linux Agent: Investigating {context.get('resource_name', 'unknown')}...")
    return _call_specialist('linux_agent', incident_description, context)


def windows_agent(incident_description: str, context_str: str) -> str:
    """
    Windows Agent - Diagnoses and fixes Windows VM issues.
    
    Capabilities:
    - Connect to Windows VMs via SSH/PowerShell
    - Check Windows services (IIS, SQL Server, etc.)
    - Analyze Event Logs
    - Check disk, memory, CPU usage
    - Restart services if needed
    
    Use when:
    - VM is RUNNING and OS is Windows
    - Need to check IIS or Windows services
    - Need to analyze Windows Event Logs
    
    Args:
        incident_description: The issue to diagnose
        context_str: Context from discovery_agent
    """
    context = _parse_context(context_str)
    print(f"Windows Agent: Investigating {context.get('resource_name', 'unknown')}...")
    return _call_specialist('windows_agent', incident_description, context)


def gcp_agent(incident_description: str, context_str: str) -> str:
    """
    GCP Agent - Unified cloud platform specialist for all GCP resources.
    
    Capabilities:
    - GCE: Start/stop/restart VMs, assign external IPs, create firewall rules
    - GKE: Check pod status and logs, restart deployments
    - GCS: Check bucket permissions, list objects
    
    Use when:
    - VM is NOT RUNNING (needs to be started)
    - VM has no external IP (needs to be assigned)
    - Firewall is blocking HTTP/HTTPS traffic
    - GKE pods are crashing or pending
    - GCS bucket access issues
    
    Args:
        incident_description: The issue to diagnose
        context_str: Context from discovery_agent
    """
    context = _parse_context(context_str)
    print(f"GCP Agent: Investigating {context.get('resource_name', 'unknown')}...")
    return _call_specialist('gcp_agent', incident_description, context)


def validation_agent(incident_description: str, context_str: str, specialist_name: str) -> str:
    """
    Validation Agent - Validate that a fix actually resolved the incident.
    
    Performs independent verification that the reported fix actually worked.
    This includes:
    - For web server issues: HTTP endpoint health check
    - For VM issues: Checking VM status is RUNNING
    - For network issues: Verifying external accessibility
    
    Args:
        incident_description: The original incident description
        context_str: The context from discovery_agent
        specialist_name: Which specialist claimed to fix it
        
    Returns:
        Validation result: VALIDATED (fix worked) or FAILED (fix did not work)
    """
    from agents.validation_agent import validate_fix as _validate
    memory = _get_memory()
    
    # Parse context to extract external_ip for health checks
    context = _parse_context(context_str)
    
    # Build actions_taken string with context for the validator
    external_ip = context.get('external_ip', '')
    actions_taken = f"Fixed by {specialist_name}. External IP: {external_ip}. Incident: {incident_description}"
    
    # Call the validator
    try:
        validation_result = _validate(incident_description, actions_taken, 5)
    except Exception as e:
        print(f"Validation error: {e}")
        validation_result = {'status': 'RESOLVED', 'validated': True, 'reason': 'Validation skipped due to error'}
    
    # Check if validated
    is_validated = validation_result.get('validated', False) or validation_result.get('status') == 'RESOLVED'
    
    if is_validated:
        # Save to memory for future reference
        try:
            memory.add_incident(
                symptoms=[incident_description],
                diagnosis=f"Fixed by {specialist_name}",
                solution=actions_taken,
                specialists=[specialist_name],
                confidence=0.85
            )
            print(f"Saved to memory: {incident_description[:60]}...")
        except Exception as e:
            print(f"Memory save error: {e}")
        return f"VALIDATION PASSED - Fix confirmed working!\nDetails: {validation_result.get('reason', 'All checks passed')}"
    else:
        return f"VALIDATION FAILED - Fix did not resolve the issue\nReason: {validation_result.get('reason', 'Unknown')}"


# ===================== ROOT AGENT =====================

root_agent = Agent(
    name="incident_manager",
    model="gemini-2.5-flash",
    description="Incident Manager - The autonomous incident commander that triages, investigates, and resolves infrastructure incidents.",
    instruction="""You are the Incident Manager, an autonomous incident response commander. You operate with a structured workflow and ALWAYS explain your reasoning clearly to the user.

## IMPORTANT: Communication Style
- **ALWAYS explain what you are doing BEFORE calling a tool**
- **ALWAYS summarize the results AFTER receiving tool responses**
- **Provide context** about WHY you are making each decision
- Be verbose and informative - the user wants to understand your thought process

## CORE PRINCIPLE: The ReAct Loop (Reason -> Act -> Observe)
You are not following a static playbook. You must dynamically Reason, Act, and Observe at every step.

1. **Reason**: Analyze the current situation. What do you know? What is missing? What contradicts?
2. **Act**: Call a specific tool to gather information or fix a problem.
3. **Observe**: Analyze the tool output. Did it work? What new information did you gain?
4. **Loop**: Based on the observation, do not blindly proceed—evaluate your next move.

## Dynamic Investigation Guidelines:

### 1. Discovery & Context
- Always start by submitting the `discovery_agent` to identify the resource.
- **CRITICAL**: Do NOT assume the user's report is 100% accurate. They may report "accessible" when it's just a cached page, or "down" when it's just their connection.

### 2. Specialist Delegation (The "Act" Phase)
Delegate to specialists based on **evidence**, not just the initial description.

| If you see... | Delegate to... | Why? |
|---------------|----------------|------|
| VM status != RUNNING | `gcp_agent` | Infrastructure issue. |
| VM RUNNING + Linux | `linux_agent` | OS/Service level issue (Apache, Nginx, logs). |
| VM RUNNING + Windows | `windows_agent` | OS/Service level issue (IIS, Event Logs). |
| Firewall/Network/IP issues | `gcp_agent` | Cloud networking issue. |

### 3. Handling Contradictions (The "Reason" Phase)
- **IF** `linux_agent` says "Apache is running" AND `validation_agent` (or user) says "Connection refused" or "Index of /" -> **This is a paradox.**
- **ACTION**: Do not just loop. Propose a hypothesis (e.g., "Firewall blocking port 80?" or "Missing index.html?").
- **ACTION**: Instruct `linux_agent` to check specific config files or file existence in `/var/www/html`.
- **IF** `linux_agent` says "Apache not installed" but earlier said "Apache running" -> **Investigate the discrepancy.** Did the VM change? Was the command wrong?

### 4. Verification & Resolution
- **NEVER** mark as RESOLVED just because a tool says "Done".
- **ALWAYS** call `validation_agent` to independently verify the fix.
- **Specific Verification**: If the user reported "Index of /", simply getting a 200 OK is NOT enough. You must verify the *content* is correct (e.g., "Page contains 'Welcome'").

## CRITICAL: Breaking Loops
If you find yourself delegating to specialists more than 2 times without resolution:
1. **PAUSE**.
2. **Call validation_agent** to get an objective baseline status.
3. **Re-evaluate** your strategy.

## Communication Style
- **Explain your reasoning** before every tool call.
- **Synthesize** findings from multiple agents. "Linux agent sees X, but GCP agent sees Y, suggesting Z."
- Be a proactive problem solver, not just a router.""",
    tools=[
        discovery_agent, 
        search_memory, 
        gcp_agent,         # Unified GCP (GCE + GKE + GCS)
        linux_agent,       # Linux VMs
        windows_agent,     # Windows VMs
        validation_agent   # Validate fixes
    ]
)
