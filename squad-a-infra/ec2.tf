variable "ami_id" {
  description = "Ubuntu 24.04 AMI ID for the chosen region"
  type        = string
}

resource "aws_instance" "cloudvote_app" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

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
