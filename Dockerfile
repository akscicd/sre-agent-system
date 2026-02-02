FROM python:3.10-slim
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser
ENV HOME=/home/appuser
RUN mkdir -p /home/appuser/.config/gcloud \
    && chown -R appuser:appuser /home/appuser
WORKDIR /app
RUN apt-get update && apt-get install -y curl gnupg openssh-client && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN chmod -R 777 /usr/local/lib/python3.10/site-packages/google/adk/cli/browser/assets/config/
COPY app/ .
RUN chown -R appuser:appuser /app
USER appuser
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-m", "google.adk.cli", "web", "--port", "8080", "--host", "0.0.0.0"]