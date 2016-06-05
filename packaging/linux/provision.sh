#!/bin/bash

function install_deps() {
	echo Installing necessary dependencies
	if which apt-get; then
		# ubuntu
		sudo apt-get -y update &&
		# trusty
		sudo apt-get install -y software-properties-common ||
		# precise
		sudo apt-get install -y python-software-properties && sudo add-apt-repository -y ppa:git-core/ppa
		sudo apt-get install -y curl python-dev git make gcc g++ libyaml-dev zlib1g-dev
	elif which yum; then
		# centos/REHL
		sudo yum -y update &&
		sudo yum install curl python-devel make gcc gcc-c++ git libyaml-devel yum-utils -y
	else
		echo 'unsupported package manager, exiting'
		exit 1
	fi
}

function install_requirements() {
	curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | sudo python
	sudo pip install pip==6.0.8 --upgrade
	sudo pip install "virtualenv>=14.0.0,<15.0.0" &&
	sudo pip install setuptools==19.1.1 --upgrade &&
	sudo pip install cloudify-agent-packager==4.0.0
}


# VERSION/PRERELEASE/BUILD must be exported as they is being read as an env var by the cloudify-agent-packager
CORE_TAG_NAME="3.4rc1"
curl https://raw.githubusercontent.com/cloudify-cosmo/cloudify-packager/$CORE_TAG_NAME/common/provision.sh -o ./common-provision.sh &&
source common-provision.sh

GITHUB_USERNAME=$1
GITHUB_PASSWORD=$2
AWS_ACCESS_KEY_ID=$3
AWS_ACCESS_KEY=$4

install_common_prereqs &&
cd ~
install_deps &&
install_requirements &&
sudo rm -rf ~/.cache
cd /tmp && cfy-ap -c /vagrant/linux/packager.yaml -f -v &&
create_md5 "tar.gz" &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3 "tar.gz" && upload_to_s3 "md5"
