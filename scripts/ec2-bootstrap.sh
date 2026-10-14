#!/usr/bin/env bash
# First-boot setup for the CloudVote EC2 instance: Docker, the AWS CLI and the
# directory CD deploys into.
#
# Terraform passes this as user_data, where it runs as root on first boot with no
# $USER set. It is also safe to run by hand over SSH. Both paths are covered below,
# which is why it uses $SUDO rather than a bare `sudo` and resolves the login user
# explicitly instead of trusting $USER.
#
# Output lands in /var/log/cloud-init-output.log on the instance.
set -euo pipefail

# root (user_data) has no sudo; a human over SSH does.
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

# The account CD logs in as, which is the one that needs the docker group.
TARGET_USER="${SUDO_USER:-${USER:-ubuntu}}"
[ "$TARGET_USER" = "root" ] && TARGET_USER="ubuntu"

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -y
$SUDO apt-get install -y ca-certificates curl unzip docker.io docker-compose-v2

# AWS CLI v2 - fetch-env.sh reads the app secrets out of SSM with it. The apt package
# is not available on Ubuntu 24.04.
if ! command -v aws >/dev/null 2>&1; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  $SUDO /tmp/aws/install
  rm -rf /tmp/aws /tmp/awscliv2.zip
fi

$SUDO systemctl enable --now docker
$SUDO usermod -aG docker "$TARGET_USER"

# Where CD copies the compose files, the scripts and the nginx config.
$SUDO mkdir -p /opt/cloudvote
$SUDO chown "$TARGET_USER":"$TARGET_USER" /opt/cloudvote

echo "Bootstrap done for $TARGET_USER. Over SSH, log out and back in so the docker group applies."
