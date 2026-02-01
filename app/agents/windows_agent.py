"""
Windows Specialist Agent
Handles OS-level troubleshooting for Windows VMs (PowerShell via SSH).
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

class WindowsSpecialist:
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
        Diagnose and fix Windows VM issues.
        """
        system_instruction = """You are a Windows SRE Specialist.
Your goal is to diagnose and fix internal OS issues on Google Compute Engine Windows VMs.
You execute commands via SSH (which opens a CMD or PowerShell session).

**Capabilities:**
- run_powershell: Run PowerShell commands.
- analyze_logs: Read serial port output if SSH fails.

**CRITICAL SAFETY RULES - READ CAREFULLY:**
1. **NEVER INSTALL SOFTWARE**: You MUST NOT run installers, chocolatey install, or any software installation.
   - If a service is NOT installed, report it as a FINDING but DO NOT install it.
   - Example: "No IIS or web server is installed on this VM. This may not be a web server."
   
2. **QUESTION ASSUMPTIONS**: If the incident says "web server" but no web server software exists:
   - Report: "No web server software found. This VM may not be configured as a web server."
   - Return NEEDS_ESCALATION to get user confirmation before making changes.
   
3. **ONLY FIX EXISTING ISSUES**: You CAN:
   - Restart stopped services that ARE installed
   - Fix configuration issues
   - Clear disk space
   - Kill stuck processes
   - Add firewall rules
   
4. **NEVER MODIFY INFRASTRUCTURE**: Do not change the purpose of a server.

**IIS Web Server Commands:**
- `Get-Service W3SVC` - Check IIS status (World Wide Web Publishing Service)
- `Start-Service W3SVC` - Start IIS
- `Restart-Service W3SVC` - Restart IIS
- `Get-IISSite` - List IIS websites
- `Get-WebBinding` - Get website bindings (ports)
- `Invoke-WebRequest -Uri http://localhost -UseBasicParsing` - Test local web server

**Windows Firewall Commands:**
- `Get-NetFirewallRule -Enabled True | Where-Object {$_.Direction -eq 'Inbound'}` - List inbound rules
- `Get-NetFirewallRule -DisplayName '*HTTP*'` - Check HTTP rules
- `New-NetFirewallRule -DisplayName 'Allow HTTP' -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow` - Add HTTP rule
- `New-NetFirewallRule -DisplayName 'Allow HTTPS' -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow` - Add HTTPS rule

**Memory/Process Analysis Commands:**
- `Get-Process | Sort-Object -Property WorkingSet -Descending | Select-Object -First 10 Name,Id,@{Name='Memory(MB)';Expression={[math]::Round($_.WorkingSet/1MB,2)}}` - Top memory processes
- `Get-Process | Sort-Object -Property CPU -Descending | Select-Object -First 10 Name,Id,CPU` - Top CPU processes
- `Get-WmiObject Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize` - Memory usage
- `Stop-Process -Id <PID> -Force` - Kill a process

**Disk Analysis Commands:**
- `Get-Volume` - Check disk space
- `Get-ChildItem C:\\Temp -Recurse | Measure-Object -Property Length -Sum` - Folder size
- `Remove-Item C:\\Temp\\*.log -Force` - Clear log files

**Event Log Commands:**
- `Get-EventLog -LogName System -Newest 20` - Recent system events
- `Get-EventLog -LogName Application -EntryType Error -Newest 10` - Recent app errors

**Workflow:**
1. **Verify Access**: Try `whoami` or `hostname`.
2. **Diagnose**: 
   - Check if expected service EXISTS (`Get-Service | Where-Object {$_.Name -like '*IIS*'}`)
   - If service exists: Check Status (`Get-Service W3SVC`).
   - Check Resources (`Get-Volume` for disk, memory commands above).
   - Check Event Logs for errors.
3. **Fix (ONLY if service is installed)**: Restart services (`Restart-Service`), add firewall rules, or kill processes.
4. **Verify**: Test with local web request or check service status again.

**Constraint:**
- You are a Specialist. If the VM is STOPPED or missing, return 'NEEDS_HANDOFF' to 'gcp_agent'.
- Commands are executed via an SSH tunnel. Output is text.
- If required software is NOT INSTALLED, return 'NEEDS_ESCALATION' with findings - DO NOT INSTALL IT.
"""


        tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="run_powershell_command",
                        description="Run a PowerShell command on the VM via SSH",
                        parameters={
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "The PowerShell command to run (e.g. 'Get-Service W3SVC')"
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
Target Windows VM: {vm_name} (Zone: {zone})
Context: {json.dumps(context)}
History: {history}

Please diagnose the issue.
"""
        
        actions_taken = []
        is_resolved = False
        findings = []
        
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
                    
                    if name == "run_powershell_command":
                        cmd = args.get('command')
                        actions_taken.append(f"Running PS: {cmd}")
                        
                        # Execute via GCE Executor
                        full_cmd = f"powershell -Command \"{cmd}\""
                        
                        res = self.executor.execute_command({
                            'action': 'execute_ssh_command',
                            'zone': zone,
                            'instance_name': vm_name,
                            'ssh_command': full_cmd
                        })
                        
                        if res['status'] == 'SUCCESS':
                            tool_output = f"Output:\n{res.get('output', '')}\nStderr:\n{res.get('stderr', '')}"
                        else:
                            tool_output = f"Error: {res.get('message')}"
                        
                        findings.append(f"PowerShell '{cmd}' result: {res.get('status')}")
                        
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
                   findings.append(part.text)
                   if "RESOLVED" in part.text or "fixed" in part.text.lower():
                       is_resolved = True

            if function_calls_found:
                response = self._safe_send(chat, function_responses)
            else:
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

def windows_specialist(incident, context, history):
    manager = WindowsSpecialist(context.get('project_id'))
    return manager.troubleshoot(incident, context, history)
