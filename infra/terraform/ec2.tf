variable "ami_id" {
  description = "Pin a specific AMI. Leave null and the newest Ubuntu 24.04 LTS for this region is used."
  type        = string
  default     = null
}

# AMI IDs differ per region and change every time Canonical publishes an image, so
# requiring one by hand meant looking it up in the console before every apply - and
# getting a stale or wrong-region id if you did not.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "cloudvote_app" {
  ami                    = coalesce(var.ami_id, data.aws_ami.ubuntu.id)
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  # scripts/ec2-bootstrap.sh existed but nothing ran it, so a fresh apply produced an
  # instance with no Docker and no /opt/cloudvote - and the first CD deploy failed on
  # `docker compose`. Running it here means the box is ready the moment it boots.
  # Changing the script replaces the instance, which is the intended behaviour: a
  # half-bootstrapped server is worse than a new one.
  user_data                   = file("${path.module}/../../scripts/ec2-bootstrap.sh")
  user_data_replace_on_change = true

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
