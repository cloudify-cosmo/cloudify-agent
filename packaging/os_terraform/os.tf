variable "GITHUB_USERNAME" {}
variable "GITHUB_PASSWORD" {}
variable "BUILD_OS_TENANT" {}
variable "BUILD_OS_USERNAME" {}
variable "BUILD_OS_PASSWORD" {}
variable "AWS_ACCESS_KEY_ID" {}
variable "AWS_SECRET_ACCESS_KEY" {}
variable "RACKSPACE_IMAGE_BUILDER_OS_AUTH_URL" {}
variable "RACKSPACE_IMAGE_BUILDER_OS_PROJECT_NAME" {}
variable "RACKSPACE_IMAGE_BUILDER_OS_PASSWORD" {}
variable "RACKSPACE_IMAGE_BUILDER_OS_USERNAME" {}
variable "REPO" {}
variable "BRANCH" {}
variable "ssh_key_file" {default = "/Users/mac/.ssh/os/build.pem"}

# Configure the Openstack Provider
provider "openstack" {
 user_name   = "${var.RACKSPACE_IMAGE_BUILDER_OS_USERNAME}"
 tenant_name = "${var.RACKSPACE_IMAGE_BUILDER_OS_PROJECT_NAME}"
 password    = "${var.RACKSPACE_IMAGE_BUILDER_OS_PASSWORD}"
 #password    = "${var.secret_key}"
 auth_url    = "${var.RACKSPACE_IMAGE_BUILDER_OS_AUTH_URL}"
 #region      = "RegionOne"
}

resource "openstack_networking_floatingip_v2" "floatingip" {
  pool = "GATEWAY_NET"
}

resource "openstack_compute_floatingip_associate_v2" "instance_floating" {
  floating_ip = "${openstack_networking_floatingip_v2.floatingip.address}"
  instance_id = "${openstack_compute_instance_v2.centos_core_agent_test.id}"
}

resource "openstack_compute_instance_v2" "centos_core_agent_test" {
  #depends_on = ["openstack_compute_floatingip_associate_v2.instance_floating"]
  name = "centos_core_agent_test"
  image_name = "CentOS-7-x86_64-GenericCloud"
  flavor_name = "m1.medium"
  key_pair = "build"
  security_groups = ["default"]

  network {
    uuid = "cd68bf9c-648e-4790-9272-7b9307d928bd"
  }

  connection {
    type = "ssh"
    user = "centos"
    #private_key = "${file("${var.ssh_key_file}")}"
    private_key = "${file("~/.ssh/os/build.pem")}"
    host = "${openstack_networking_floatingip_v2.floatingip.address}"
    timeout = "50m"
    agent = "false"
  }

  provisioner "file" {
    source = "../"
    destination = "~"

  }

  provisioner "remote-exec" {
    inline = [
      "chmod +x ~/linux/provision.sh",
      "~/linux/provision.sh centosGITHUB_USERNAME} ${var.GITHUB_PASSWORD} ${var.AWS_ACCESS_KEY_ID} ${var.AWS_SECRET_ACCESS_KEY} ${var.REPO} ${var.BRANCH}"
    ]
  }
}
