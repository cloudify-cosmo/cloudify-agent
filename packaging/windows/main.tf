variable "VERSION" {}
variable "PRERELEASE" {}
variable "password" {}
variable "DEV_BRANCH" {}


provider "aws" {
  region = "eu-west-1"
}

data "aws_ami" "windows_agent_builder" {
  most_recent = true

  filter {
    name   = "name"
    values = ["Windows_Server-2016-English-Full-Base-*"]
  }

  owners = ["801119661308"] # This is the amazon owner ID for a bunch of their marketplace images
}

resource "aws_instance" "builder" {
  ami           = "${data.aws_ami.windows_agent_builder.id}"
  instance_type = "m3.medium"
  iam_instance_profile = "windows_agent_builder"

  tags = {
    Name = "Windows Agent Builder"
  }

  timeouts {
    create = "15m"  # Win2016 can take its time starting
  }

  provisioner "file" {
    source      = "win_agent_builder.ps1"
    destination = "C:\\Users\\Administrator\\win_agent_builder.ps1"
    connection {
      type     = "winrm"
      port     = 5986
      https    = true
      insecure = true
      user     = "Administrator"
      password = "${var.password}"
    }
  }

  provisioner "remote-exec" {
    inline = [ "powershell.exe -File C:\\Users\\Administrator\\win_agent_builder.ps1 ${var.VERSION} ${var.PRERELEASE} ${var.DEV_BRANCH}" ]
    connection {
      type     = "winrm"
      port     = 5986
      https    = true
      insecure = true
      user     = "Administrator"
      password = "${var.password}"
    }
  }
}
