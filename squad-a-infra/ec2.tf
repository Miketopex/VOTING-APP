variable "ami_id" {
  description = "Ubuntu 24.04 AMI ID for the chosen region"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "Name of the existing EC2 key pair for SSH access"
  type        = string
}

variable "subnet_id" {
  description = "Public subnet ID to launch the instance into"
  type        = string
}

variable "security_group_id" {
  description = "Security group ID allowing 80, 443, 22"
  type        = string
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile granting CloudWatch, SSM, S3 access"
  type        = string
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "prod"
}

resource "aws_instance" "cloudvote_app" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile   = var.iam_instance_profile_name

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name        = "cloudvote-${var.environment}-ec2"
    Environment = var.environment
    Project     = "cloudvote"
  }
}

resource "aws_eip" "cloudvote_eip" {
  instance = aws_instance.cloudvote_app.id
  domain   = "vpc"

  tags = {
    Name = "cloudvote-${var.environment}-eip"
  }
}
