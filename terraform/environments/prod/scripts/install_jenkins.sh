#!/bin/bash

apt-get update
apt-get install -y openjdk-17-jre docker.io

curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null
echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/ | tee /etc/apt/sources.list.d/jenkins.list > /dev/null
apt-get update
apt-get install -y jenkins

usermod -aG docker jenkins

snap install google-cloud-cli --classic

systemctl enable jenkins
systemctl start jenkins
