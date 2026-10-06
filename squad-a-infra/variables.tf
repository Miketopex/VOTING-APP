variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "project" {
  type    = string
  default = "cloudvote"
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "instance_type" {
  description = "t3.micro is free-tier eligible (1 GB RAM + 2 GB swap is enough for the 5 containers); t3.small gives more headroom"
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "Name of an EXISTING EC2 key pair for SSH"
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "Who may SSH in. GitHub Actions deploys over SSH from changing IPs, so 0.0.0.0/0 is the simple default (key-only login)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "admin_username" {
  description = "Username of the first CloudVote administrator"
  type        = string
  default     = "admin"
}

variable "alert_email" {
  description = "E-mail that receives CloudWatch alarms (confirm the subscription e-mail!)"
  type        = string
}

variable "backup_retention_days" {
  type    = number
  default = 14
}
