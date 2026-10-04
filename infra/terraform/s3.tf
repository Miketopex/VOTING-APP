variable "backup_bucket_name" {
  description = "Globally unique S3 bucket name for CloudVote backups"
  type        = string
}

resource "aws_s3_bucket" "cloudvote_backups" {
  bucket = var.backup_bucket_name

  tags = {
    Name        = "cloudvote-${var.environment}-backups"
    Environment = var.environment
    Project     = "cloudvote"
  }
}

resource "aws_s3_bucket_public_access_block" "cloudvote_backups" {
  bucket = aws_s3_bucket.cloudvote_backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudvote_backups" {
  bucket = aws_s3_bucket.cloudvote_backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "cloudvote_backups" {
  bucket = aws_s3_bucket.cloudvote_backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudvote_backups" {
  bucket = aws_s3_bucket.cloudvote_backups.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"

    filter {
      prefix = "backups/"
    }

    expiration {
      days = 14
    }
  }
}
