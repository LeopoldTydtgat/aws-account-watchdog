# Phase 2, step 1: the test range.
# A small network for the security patrol to guard and for game days to
# break. No instances and no NAT gateway, so it costs nothing (D-003).

locals {
  range_cidr = "10.20.0.0/16"
}

resource "aws_vpc" "test_range" {
  cidr_block           = local.range_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "watchdog-test-range" }
}

# Strips every rule from the VPC's built-in default security group, so
# nothing can accidentally inherit "allow all from each other" (CIS 5.4).
resource "aws_default_security_group" "test_range" {
  vpc_id = aws_vpc.test_range.id

  tags = { Name = "watchdog-range-default-locked" }
}

# Free. Only gives the public subnet a route to the internet; nothing
# can use it because no instances or public IPs exist.
resource "aws_internet_gateway" "test_range" {
  vpc_id = aws_vpc.test_range.id

  tags = { Name = "watchdog-range-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.test_range.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = "eu-north-1a"
  map_public_ip_on_launch = false

  tags = { Name = "watchdog-range-public" }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.test_range.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "eu-north-1a"

  tags = { Name = "watchdog-range-private" }
}

# What makes a subnet "public" is only this: a route to an internet gateway.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.test_range.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.test_range.id
  }

  tags = { Name = "watchdog-range-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# No internet route at all. Without a NAT gateway (~$32/month, rejected
# in D-003) nothing here can reach out, and that is fine for a range.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.test_range.id

  tags = { Name = "watchdog-range-private" }
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# Compliant baseline: HTTPS open to the world is normal for a web tier.
resource "aws_security_group" "range_web" {
  name        = "watchdog-range-web"
  description = "Test range web tier: HTTPS from anywhere"
  vpc_id      = aws_vpc.test_range.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Compliant baseline: SSH only from inside the range. Game Day 01 opens
# this to 0.0.0.0/0 in the console and times how fast the patrol reacts.
resource "aws_security_group" "range_admin" {
  name        = "watchdog-range-admin"
  description = "Test range admin access: SSH from inside the VPC only"
  vpc_id      = aws_vpc.test_range.id

  ingress {
    description = "SSH from inside the range"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [local.range_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
