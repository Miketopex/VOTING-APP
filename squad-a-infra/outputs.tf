output "ec2_public_ip" {
  description = "Elastic IP address of the CloudVote EC2 instance"
  value       = aws_eip.cloudvote_eip.public_ip
}

output "ec2_instance_id" {
  description = "ID of the CloudVote EC2 instance"
  value       = aws_instance.cloudvote_app.id
}

output "s3_backup_bucket_name" {
  description = "Name of the S3 backup bucket"
  value       = aws_s3_bucket.cloudvote_backups.bucket
}

output "s3_backup_bucket_arn" {
  description = "ARN of the S3 backup bucket"
  value       = aws_s3_bucket.cloudvote_backups.arn
}
