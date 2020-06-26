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

  user_data = "<script>\nwinrm quickconfig -q\nwinrm set winrm/config '@{MaxTimeoutms=\"1800000\"}'\nwinrm set winrm/config/winrs '@{MaxMemoryPerShellMB=\"300\"}'\nwinrm set winrm/config/service '@{AllowUnencrypted=\"true\"}'\nwinrm set winrm/config/service/auth '@{Basic=\"true\"}\n</script>\n<powershell>\nnetsh advfirewall firewall add rule name=\"WinRM 5985\" protocol=TCP dir=in localport=5985 action=allow\nnetsh advfirewall firewall add rule name=\"WinRM 5986\" protocol=TCP dir=in localport=5986 action=allow\nnetsh advfirewall firewall add rule name=\"RDP for troubleshooting\" protocol=TCP dir=in localport=3389 action=allow\n$PSDefaultParameterValues['*:Encoding'] = 'utf8'\n$user = [ADSI]\"WinNT://localhost/Administrator\"\n$user.SetPassword(\"${var.password}\")\n$user.SetInfo()\n</powershell>"


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
