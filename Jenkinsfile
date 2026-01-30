pipeline {
    agent any

    environment {
        PROJECT_ID = 'sre-agent-prod'
        REGION = 'us-central1'
        REPO_NAME = 'sre-agent-repo'
        IMAGE_TAG = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/sre-agent:${env.BUILD_NUMBER}"
        SERVICE_NAME = 'sre-agent-service'
        // Mount sensitive data using Secret Manager in Cloud Run, NOT here
    }

    stages {
        stage('Test & Lint') {
            steps {
                sh 'pip install pylint pytest'
                sh 'pylint agents/ || true' // Warn only for demo
            }
        }

        stage('Build & Push') {
            steps {
                // Authenticate Docker using VM Identity
                sh 'gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet'
                sh "docker build -t ${IMAGE_TAG} ."
                sh "docker push ${IMAGE_TAG}"
            }
        }

        stage('Deploy to Cloud Run') {
            steps {
                sh """
                    gcloud run deploy ${SERVICE_NAME} \\
                        --image ${IMAGE_TAG} \\
                        --region ${REGION} \\
                        --service-account sre-agent-runtime@${PROJECT_ID}.iam.gserviceaccount.com \\
                        --allow-unauthenticated \\
                        --set-env-vars GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_GENAI_USE_VERTEXAI=true \\
                        --port 8080
                """
            }
        }
    }
}
