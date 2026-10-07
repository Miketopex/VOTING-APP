# ---------------------------------------------------------------------
#  Network: one VPC with a public subnet for the EC2 instance.
#  PostgreSQL and Redis run INSIDE Docker on that instance on a private
#  Docker network, so they need no subnet of their own and publish no ports.
# ---------------------------------------------------------------------
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "${var.project}-${var.environment}"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "${local.name}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name}-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 0) # 10.30.0.0/24
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${local.name}-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Keeps backup uploads to S3 on the AWS network (free)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]
  tags              = { Name = "${local.name}-s3-endpoint" }
}

# ---------------------------------------------------------------------
#  Security group: only 80/443 (and SSH) reach the instance.
#  5432 (PostgreSQL) and 6379 (Redis) are NOT opened – ever.
# ---------------------------------------------------------------------
resource "aws_security_group" "web" {
  name        = "${local.name}-web-sg"
  description = "CloudVote EC2: HTTP/HTTPS from the internet, SSH for deployments"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP (redirect to HTTPS, Let's Encrypt challenge)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "SSH (key-only) for GitHub Actions deploys and admins"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidrs
  }
  egress {
    description = "Outbound: packages, Docker Hub, AWS APIs"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${local.name}-web-sg" }
}
