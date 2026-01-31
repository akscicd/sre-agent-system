#!/bin/bash

sudo apt-get update
sudo apt-get install -y openjdk-21-jre docker.io

sudo wget -O /etc/apt/keyrings/jenkins-keyring.asc \
  https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key
echo "deb [signed-by=/etc/apt/keyrings/jenkins-keyring.asc]" \
  https://pkg.jenkins.io/debian-stable binary/ | sudo tee \
  /etc/apt/sources.list.d/jenkins.list > /dev/null
sudo apt update
sudo apt install -y jenkins

sudo usermod -aG docker jenkins

sudo snap install google-cloud-cli --classic

sudo systemctl enable jenkins
sudo systemctl start jenkins
