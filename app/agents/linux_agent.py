"""
Linux Specialist Agent
Handles OS-level troubleshooting for Linux VMs (SSH, Services, Logs).
"""

from google import genai
from google.genai import types
from tools.gce_executor import GCEExecutorTool
import yaml
import os
import yaml
import json
import time

def load_config():
    with open('adk.yaml', 'r') as f:
        content = os.path.expandvars(f.read())
        return yaml.safe_load(content)

class LinuxSpecialist:
    def __init__(self, project_id: str):
        self.project_id = project_id  # This is the project associated with the incident, used for GCE operations.
        self.config = load_config()
        # Use the configuration project for Vertex AI where the service is enabled.
        vertex_project = self.config['gcp']['project_id']
        self.client = genai.Client(vertexai=True, project=vertex_project, location=self.config['gcp']['region'])
        # Use the incident project for Google Compute Engine operations.
        self.executor = GCEExecutorTool(project_id, dry_run=self.config['execution']['dry_run'])
        
        self.model_name = self.config['models']['default']

    def troubleshoot(self, incident_description: str, context: dict, history: list = None) -> dict:
        """
        Diagnose and fix Linux VM issues.
        """
        system_instruction = """You are a Linux SRE Specialist.
Your goal is to diagnose and fix internal OS issues on Google Compute Engine VMs via SSH.

**Capabilities:**
- access_shell: Run commands via SSH. (e.g., 'systemctl status apache2', 'df -h', 'cat /var/log/syslog')
- analyze_logs: Read serial port output if SSH fails.

**CRITICAL SAFETY RULES - READ CAREFULLY:**
1. **NEVER INSTALL SOFTWARE**: You MUST NOT run apt install, yum install, or any package installation commands.
   - If a service is NOT installed, report it as a FINDING but DO NOT install it.
   - Example: "No web server (Apache/Nginx) is installed on this VM. This may not be a web server."
   
2. **QUESTION ASSUMPTIONS**: If the incident says "web server" but no web server software exists:
   - Report: "No web server software found. This VM may not be configured as a web server."
   - Return NEEDS_ESCALATION to get user confirmation before making changes.
   
3. **ONLY FIX EXISTING ISSUES**: You CAN:
   - Restart stopped services that ARE installed
   - Fix configuration issues
   - Clear disk space (delete log files, clear temp)
   - Kill stuck processes
   
4. **NEVER MODIFY INFRASTRUCTURE**: Do not change the purpose of a server.

**Disk Analysis Commands:**
- `df -h` - Check disk usage (CRITICAL: >90% = problem)
- `du -sh /var/log/*` - Find large log directories
- `find / -type f -size +100M 2>/dev/null | head -10` - Find large files
- `sudo rm /var/log/*.gz` - Clear old compressed logs
- `sudo truncate -s 0 /var/log/bigfile.log` - Truncate a specific large log

**Memory/Process Analysis Commands:**
- `free -h` - Check memory usage
- `top -b -n 1 | head -20` - Top processes by CPU
- `ps aux --sort=-%mem | head -10` - Top processes by memory
- `pgrep -a <process>` - Find specific processes
- `kill -9 <pid>` - Kill runaway process (with caution)

**Workflow:**
1. **Verify Access**: Try `uptime` or `id`.
2. **Diagnose**: 
   - Check if expected service EXISTS (`which apache2`, `dpkg -l | grep apache`)
   - If service exists: Check Status (`systemctl status <service>`).
   - Check Resources (`df -h` for disk, `free -h` for memory).
   - Check Logs (`tail -n 50 /var/log/syslog`).
3. **Fix (ONLY if service is installed)**:
   - Restart services
   - Clear disk space (delete old logs)
   - Kill stuck processes
4. **Verify**: Run a curl/wget locally or check service status again.

**SPECIAL HANDLING - DISK FULL:**
If disk usage is >95% and you CANNOT free enough space:
- Report: "Disk is critically full at X%. Unable to free sufficient space."
- Return NEEDS_HANDOFF to 'gcp_agent' with: "Disk resize needed from XGB to YGB"
- The gcp_agent can resize the disk at the platform level.

**Constraint:**
- You are a Specialist. If the VM is STOPPED or missing, return 'NEEDS_HANDOFF' to 'gcp_agent'.
- If you can't SSH (Connection Refused/Timeout) after retries, return 'NEEDS_HANDOFF' to 'gcp_agent'.
- If required software is NOT INSTALLED, return 'NEEDS_ESCALATION' with findings - DO NOT INSTALL IT.
- If disk needs to be RESIZED (not just cleaned), return 'NEEDS_HANDOFF' to 'gcp_agent'.
- **DO NOT** use chained commands like `cmd && echo yes || echo no`. This masks errors. Run the command directly and check the exit code/output.
- **Double Check**: If `which` fails, check `dpkg -l` or `rpm -qa` before declaring "Not Installed".
"""


        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="run_linux_command",
                        description="Run a shell command on the VM via SSH",
                        parameters={
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "The shell command to run (e.g. 'sudo systemctl restart apache2')"
                                }
                            },
                            "required": ["command"]
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

        # Context Preparation
        vm_name = context.get('resource_name', 'unknown')
        zone = context.get('zone', 'unknown')
        
        prompt = f"""
Incident: {incident_description}
Target VM: {vm_name} (Zone: {zone})
Context: {json.dumps(context)}
History: {history}

Please diagnose the issue.
"""
        
        actions_taken = []
        is_resolved = False
        findings = []
        
        # Retry logic for initial message
        response = self._safe_send(chat, prompt)
        
        max_steps = 5
        step = 0
        
        while response and step < max_steps:
            step += 1
            parts = response.candidates[0].content.parts
            
            function_calls_found = False
            function_responses = []
            
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls_found = True
                    fc = part.function_call
                    name = fc.name
                    args = dict(fc.args)
                    
                    if name == "run_linux_command":
                        cmd = args.get('command')
                        actions_taken.append(f"Running: {cmd}")
                        
                        # Execute via GCE Executor
                        res = self.executor.execute_command({
                            'action': 'execute_ssh_command',
                            'zone': zone,
                            'instance_name': vm_name,
                            'ssh_command': cmd
                        })
                        
                        if res['status'] == 'SUCCESS':
                            tool_output = f"Return Code: {res.get('return_code', 0)}\nOutput:\n{res.get('output', '')}\nStderr:\n{res.get('stderr', '')}"
                            output_preview = res.get('output', '')[:150].replace('\n', ' ')
                            findings.append(f"[{cmd}] → {output_preview}...")
                        elif res['status'] == 'SSH_FAILED':
                            tool_output = f"SSH FAILED: {res.get('message', 'Unknown error')}"
                            findings.append(f"CRITICAL: Cannot SSH to VM - {res.get('message', 'connection failed')}")
                            # If SSH fails, we can't continue investigating
                            is_resolved = False
                            # We still need to return the response for this call
                        else:
                            tool_output = f"Error: {res.get('message')}"
                            findings.append(f"[{cmd}] → ERROR: {res.get('message', 'unknown')[:100]}")
                        
                        function_responses.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response={"result": tool_output}
                            )
                        ))
                    else:
                        function_responses.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=name,
                                response={"result": "Unknown tool"}
                            )
                        ))
                elif hasattr(part, 'text') and part.text:
                    # Collect text parts as findings/logic
                    findings.append(part.text)
                    if "RESOLVED" in part.text or "fixed" in part.text.lower():
                        is_resolved = True

            if function_calls_found:
                # Send all responses back in one turn
                response = self._safe_send(chat, function_responses)
            else:
                # No function calls, assumption is we are done or the model is asking a question
                # For this agent, we treat it as done if it stops calling tools
                break
        
        return {
            "status": "RESOLVED" if is_resolved else "NEEDS_HANDOFF",
            "findings": findings,
            "actions_taken": actions_taken,
            "solution": response.text if is_resolved else None,
            "suggested_specialist": "gcp_platform" if not is_resolved else None
        }

    def _safe_send(self, chat, content):
        retries = 3
        backoff = 10
        while retries > 0:
            try:
                time.sleep(2) # Base pacing
                return chat.send_message(content)
            except Exception as e:
                if "429" in str(e) or "Resource exhausted" in str(e):
                    print(f"429 Hit. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2 # Exponential backoff
                    retries -= 1
                else:
                    raise e
        return None

# Standalone function for simple import
def linux_specialist(incident, context, history):
    manager = LinuxSpecialist(context.get('project_id'))
    return manager.troubleshoot(incident, context, history)
