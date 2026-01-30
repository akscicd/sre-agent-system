"""
Validator Agent - Validates if fixes resolved the issue
"""

from google import genai
from google.genai import types
from google import genai
from google.genai import types
from tools.validator_tools import ValidatorTools
import yaml
import time
import json
import yaml
import time

def load_config():
    """Load the configuration from the yaml file."""
    with open('adk.yaml', 'r') as f:
        return yaml.safe_load(f)

def validate_fix(incident_description: str, actions_taken: str, wait_seconds: int = 10) -> dict:
    """
    Validator agent that checks if the fix worked.
    
    Args:
        incident_description: Original incident
        actions_taken: Actions that were performed
        wait_seconds: Time to wait before validation
        
    Returns:
        Validation result
    """
    
    config = load_config()
    project_id = config['gcp']['project_id']
    model_name = config['models']['default']
    
    client = genai.Client(vertexai=True, project=project_id, location=config['gcp']['region'])
    validator_tools = ValidatorTools(project_id)
    
    # Wait for the changes to propagate before validating.
    if wait_seconds > 0:
        print(f"  Waiting {wait_seconds}s for changes to take effect...")
        time.sleep(wait_seconds)
    
    system_instruction = """You are an Autonomous Validation Agent (QA).

Your Goal: Verify if the system is HEALTHY after a fix.
Do NOT trust that the fix worked. Verify it independently.

Your workflow:
1. Analyze the 'Original Incident' and 'Actions Taken'.
2. Decide HOW to verify the fix based on the incident type:
   - If Incident="Website Down" or "502 Error" -> Use `check_endpoint_health(url)`.
   - If Incident="Private VM Web Server" -> Use `verify_internal_endpoint(zone, instance)`.
   - If Incident="VM Down" -> Use `verify_gce_state(RUNNING)`.
   - If Incident="Pod Crash" -> Use `verify_gke_pod_status(Running)`.
3. execute the verification tool.
4. Return a STRICT status: RESOLVED, FAILED, or INCONCLUSIVE.

CRITICAL:
- Do NOT just look at logs unless there is no other way. PROBE the system.
- Verify CONTENT, not just status codes. If user reported "Index of /", check that it is GONE.
- FIRST action must be a tool call."""

    tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="check_endpoint_health",
                    description="Check HTTP endpoint health",
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "timeout": {"type": "integer"},
                            "expected_content": {"type": "string", "description": "Optional text to verify in response body"}
                        },
                        "required": ["url"]
                    }
                ),
                types.FunctionDeclaration(
                    name="verify_gce_state",
                    description="Verify GCE instance is RUNNING",
                    parameters={
                        "type": "object",
                        "properties": {
                            "zone": {"type": "string"},
                            "instance": {"type": "string"},
                            "expected_status": {"type": "string"}
                        },
                        "required": ["zone", "instance"]
                    }
                ),
                types.FunctionDeclaration(
                    name="verify_internal_endpoint",
                    description="Verify internal web server via SSH (curl localhost)",
                    parameters={
                        "type": "object",
                        "properties": {
                            "zone": {"type": "string"},
                            "instance": {"type": "string"},
                            "port": {"type": "integer", "description": "Port to check (default 80)"}
                        },
                        "required": ["zone", "instance"]
                    }
                ),
                types.FunctionDeclaration(
                    name="verify_gke_pod_status",
                    description="Verify GKE pod is Running",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                            "cluster": {"type": "string"},
                            "namespace": {"type": "string"},
                            "pod_name": {"type": "string"},
                            "expected_phase": {"type": "string"}
                        },
                        "required": ["location", "cluster", "pod_name"]
                    }
                ),
                types.FunctionDeclaration(
                    name="check_quota",
                    description="Check resource quota availability",
                    parameters={
                        "type": "object",
                        "properties": {
                            "region": {"type": "string"},
                            "resource_type": {"type": "string"}
                        },
                        "required": ["region"]
                    }
                ),
                types.FunctionDeclaration(
                    name="estimate_cost",
                    description="Estimate cost of an action",
                    parameters={
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "resource_details": {"type": "string"}
                        },
                        "required": ["action"]
                    }
                )
            ]
        )
    ]
    
    config_gen = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools,
        temperature=0.1
    )
    
    chat = client.chats.create(model=model_name, config=config_gen)
    
    prompt = f"""Validate this resolution:

Original Incident: {incident_description}

Actions Taken: {actions_taken}

Verify if the service is fully restored."""

    response = chat.send_message(prompt)
    
    # Handle the function calls from the model.
    while hasattr(response.candidates[0].content.parts[0], 'function_call') and response.candidates[0].content.parts[0].function_call:
        function_call = response.candidates[0].content.parts[0].function_call
        function_name = function_call.name
        args = dict(function_call.args)
        
        if function_name == "check_endpoint_health":
            result = validator_tools.check_endpoint_health(
                url=args.get("url"),
                timeout=int(args.get("timeout", 10))
            )
        elif function_name == "verify_gce_state":
            result = validator_tools.verify_gce_state(
                zone=args.get("zone"),
                instance=args.get("instance"),
                expected_status=args.get("expected_status", "RUNNING")
            )
        elif function_name == "verify_gke_pod_status":
            result = validator_tools.verify_gke_pod_status(
                location=args.get("location"),
                cluster=args.get("cluster"),
                namespace=args.get("namespace", "default"),
                pod_name=args.get("pod_name"),
                expected_phase=args.get("expected_phase", "Running")
            )
        elif function_name == "verify_internal_endpoint":
             result = validator_tools.verify_internal_endpoint(
                 zone=args.get("zone"),
                 instance=args.get("instance"),
                 port=int(args.get("port", 80))
            )
        elif function_name == "check_quota":
             result = validator_tools.check_quota(
                region=args.get("region", "us-central1"),
                resource_type=args.get("resource_type", "compute.instances")
             )
        elif function_name == "estimate_cost":
             result = validator_tools.estimate_cost(
                action=args.get("action"),
                resource_details=args.get("resource_details", "")
             )
        else:
            result = {"status": "ERROR", "message": "Function not found"}
        
        response = chat.send_message(
            types.Part(
                function_response=types.FunctionResponse(
                    name=function_name,
                    response={"result": json.dumps(result)}
                )
            )
        )
    
    validation_text = response.text
    
    # Parse the status from the validation text.
    status = "INCONCLUSIVE"
    if "RESOLVED" in validation_text.upper() and "NOT" not in validation_text.upper() and "FAILED" not in validation_text.upper():
        status = "RESOLVED"
    elif "FAILED" in validation_text.upper() or "NOT RESOLVED" in validation_text.upper():
        status = "FAILED"
    
    return {
        "status": status,
        "details": str(validation_text) if validation_text else "No validation details provided.",
        "timestamp": time.time()
    }


__all__ = ['validate_fix']
