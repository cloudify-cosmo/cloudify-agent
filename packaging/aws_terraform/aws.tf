variable "GITHUB_USERNAME" {}
variable "GITHUB_PASSWORD" {}
variable "AWS_ACCESS_KEY_ID" {}
variable "AWS_SECRET_ACCESS_KEY" {}
variable "REPO" {}
variable "BRANCH" {}


# Configure the AWS Provider
provider "aws" {
  access_key = "${var.AWS_ACCESS_KEY_ID}"
  secret_key = "${var.AWS_SECRET_ACCESS_KEY}"
  region     = "eu-west-1"
}

resource "aws_instance" "centos_core_agent-test" {
  ami           = "ami-e476b49d"
  instance_type = "m3.medium"
  key_name = "vagrant_build"
  security_groups = ["vagrant_linux_build"]
  tags {
    "Name" = "centos_core_agent-test"
  }

  connection {
     type = "ssh"
     user = "centos"
     private_key = "${file("~/.ssh/aws/vagrant_build.pem")}"
     timeout = "30m"
     agent = "false"
  }

  provisioner "file" {
      source = "linux/provision.sh"
      destination = "~/provision.sh"

  }

  provisioner "remote-exec" {
      inline = [
        "chmod +x ~/provision.sh",
        "~/provision.sh ${var.GITHUB_USERNAME} ${var.GITHUB_PASSWORD} ${var.AWS_ACCESS_KEY_ID} ${var.AWS_SECRET_ACCESS_KEY} ${var.REPO} ${var.BRANCH}"
      ]
  }

}

