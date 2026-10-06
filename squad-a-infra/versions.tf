terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # For a team project, keep state in S3 so everyone shares it.
  # Create the bucket once by hand, then uncomment:
  # backend "s3" {
  #   bucket = "cloudvote-tfstate-<your-unique-suffix>"
  #   key    = "prod/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "CloudVote"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
