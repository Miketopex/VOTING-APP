#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y ca-certificates curl unzip docker.io docker-compose-v2

# AWS CLI v2 (the apt package is not available on Ubuntu 24.04)
if ! command -v aws >/dev/null 2>&1; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  sudo /tmp/aws/install
  rm -rf /tmp/aws /tmp/awscliv2.zip
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

sudo mkdir -p /opt/cloudvote
sudo chown "$USER":"$USER" /opt/cloudvote

echo "Bootstrap done. Log out and back in so the docker group applies."
