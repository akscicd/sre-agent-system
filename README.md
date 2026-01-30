# SRE Multi-Agent System for ADK Web

Multi-agent incident response system built with Google's Agent Development Kit.

## Prerequisites

- Python 3.10+
- GCP Free Tier account
- Google Cloud SDK (`gcloud`)
- Agent Development Kit CLI

## Installation

### 1. Install ADK CLI

```bash
pip install google-adk google-genai
```

### 2. Clone and Setup

```bash
# Create project directory
mkdir sre-agent-system
cd sre-agent-system

# Copy all files to their respective locations

# Set up credentials
export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/credentials.json"

# Update adk.yaml with your project ID
# Replace YOUR_PROJECT_ID with your actual GCP project ID
```

### 3. Enable GCP APIs

```bash
gcloud services enable aiplatform.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable compute.googleapis.com
gcloud services enable container.googleapis.com
```

### 4. Create Service Account

```bash
# Create service account
gcloud iam service-accounts create sre-agent-sa \
    --display-name="SRE Agent Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:sre-agent-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/logging.viewer"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:sre-agent-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/compute.viewer"

# Create key
gcloud iam service-accounts keys create credentials.json \
    --iam-account=sre-agent-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

## Running with ADK Web

### Start the ADK Web Server

```bash
adk web
```

This will:
- Start a local web server (usually on http://localhost:8000)
- Load your agents
- Provide a web interface to interact with the incident manager

### Using the Web Interface

1. Open your browser to http://localhost:8000
2. You'll see the Incident Manager agent
3. Enter an incident description like:
   - "GCE instance web-server-01 in us-central1-a is not responding"
   - "GKE cluster prod-cluster has pods stuck in Pending state"
4. Watch the agents collaborate to resolve the issue

## Testing Without ADK Web

You can also test the agents programmatically:

```python
from agents.incident_manager import handle_incident

result = handle_incident("GCE instance web-server-01 is down")
print(result)
```

## Configuration

Edit `adk.yaml` to configure:
- GCP project ID
- Execution mode (dry_run: true/false)
- Model selection
- Logging settings

## Project Structure

```
sre-agent-system/
├── adk.yaml                    # ADK configuration
├── pyproject.toml              # Python project config
├── agents/
│   ├── __init__.py
│   ├── agent.py               # Root agent (Incident Manager)
│   ├── log_agent.py           # Log fetching
│   ├── gce_troubleshooter.py  # GCE handler
│   ├── gke_troubleshooter.py  # GKE handler
│   └── validator_agent.py     # Validation
├── tools/
│   ├── __init__.py
│   ├── log_fetcher.py          # Cloud Logging
│   ├── gce_executor.py         # GCE commands
│   ├── gke_executor.py         # GKE commands
│   ├── gcs_executor.py         # GCS commands
│   └── validator_tools.py      # Independent validation
└── README.md
```

## Key Features

-   **Deep Diagnostics**:
    -   **GCE**: SSH execution (with IAP tunneling), Serial Port monitoring, IP-to-Instance resolution.
    -   **GKE**: Pod logs, events, `kubectl describe`, automatic namespace discovery.
    -   **GCS**: Permission checks (IAM), Metadata analysis (PAP status), Object listing.
-   **Autonomous Validation**: A dedicated Validator Agent that proactively probes endpoints and resources to verify fixes.
    -   **Private VM Support**: Uses SSH tunneling to run local checks (`curl localhost`) on private instances.
-   **Resilient Workflow**: The Root Agent implements a **Retry Loop**. If validation fails, it re-issues the troubleshooting task with failure context, promoting self-correction.

## Safety Features

- **Dry Run Mode**: Enabled by default (set in adk.yaml)
- **No actual changes** made to infrastructure unless dry_run: false
-All actions are logged
- Validation after every fix

## Troubleshooting

### "Project ID not found"
Update `adk.yaml` with your actual GCP project ID

### "Permission denied"
Ensure service account has correct IAM roles

### "API not enabled"
Run the `gcloud services enable` commands above

## Next Steps

1. Test with sample incidents
2. Review agent decision logs
3. Adjust system instructions in agent files
4. Add more service types (Cloud SQL, etc.)
5. Enable real execution (dry_run: false) when ready
