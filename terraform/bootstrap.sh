#!/bin/bash
export PROJECT_ID="sre-agent-prod"
export REGION="us-central1"

echo "--- Checking Project $PROJECT_ID ---"
if gcloud projects describe $PROJECT_ID > /dev/null 2>&1; then
  echo "Project $PROJECT_ID already exists."
else
  echo "Creating Project $PROJECT_ID..."
  gcloud projects create $PROJECT_ID --name="SRE Agent Prod"
  
  if [ -z "$BILLING_ACCOUNT_ID" ]; then
    echo -n "Enter Billing Account ID (Press Enter to skip): "
    read BILLING_ACCOUNT_ID
  fi

  if [ -n "$BILLING_ACCOUNT_ID" ]; then
    echo "Linking Billing Account $BILLING_ACCOUNT_ID..."
    gcloud beta billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT_ID
  else
    echo "WARNING: Project created but Billing not linked. Please link billing manually in Console."
  fi
fi


echo "--- Setting Project Context ---"
gcloud config set project $PROJECT_ID


echo "--- Enabling Required APIs ---"
gcloud services enable \
  compute.googleapis.com \
  iam.googleapis.com \
  storage-component.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  aiplatform.googleapis.com



echo "--- Creating State Bucket ---"
if ! gsutil ls -b gs://akscicd-tfstate > /dev/null 2>&1; then
  gsutil mb -p $PROJECT_ID -l $REGION -b on gs://akscicd-tfstate
  echo "Created gs://akscicd-tfstate"
else
  echo "Bucket gs://akscicd-tfstate already exists."
fi


echo "--- Creating Terraform Runner Service Account ---"
RUNNER_SA_NAME="terraform-runner"
RUNNER_SA_EMAIL="$RUNNER_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe $RUNNER_SA_EMAIL > /dev/null 2>&1; then
  gcloud iam service-accounts create $RUNNER_SA_NAME \
    --display-name="Terraform Runner Service Account"
  echo "Created Service Account: $RUNNER_SA_EMAIL"
else
  echo "Service Account $RUNNER_SA_EMAIL already exists."
fi

echo "--- Granting Permissions to Runner ---"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$RUNNER_SA_EMAIL" \
  --role="roles/editor" > /dev/null

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$RUNNER_SA_EMAIL" \
  --role="roles/iam.securityAdmin" > /dev/null

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$RUNNER_SA_EMAIL" \
  --role="roles/storage.admin" > /dev/null

echo ""
echo "--- Bootstrap Complete! ---"
echo "Terraform Runner Email: $RUNNER_SA_EMAIL"
echo "You can now impersonate this SA or use your own credentials to run terraform."
