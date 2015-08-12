#!/bin/bash -e

function install_deps
{
	echo Installing necessary dependencies
	if which apt-get; then
		# ubuntu
		sudo apt-get -y update &&
		# trusty
		sudo apt-get install -y software-properties-common ||
		#precise
		sudo apt-get install -y python-software-properties
		sudo add-apt-repository -y ppa:git-core/ppa
		sudo apt-get install -y curl python-dev git make gcc libyaml-dev zlib1g-dev
	elif which yum; then
		# centos/REHL
		sudo yum -y update
		sudo yum install curl python-devel make gcc git libyaml-devel -y
		# this is required to build pyzmq under centos/RHEL
		sudo yum install -y zeromq-devel -c http://download.opensuse.org/repositories/home:/fengshuo:/zeromq/CentOS_CentOS-6/home:fengshuo:zeromq.repo
	else
		echo 'unsupported package manager, exiting'
		exit 1
	fi
}

function install_pip
{
	curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | sudo python
	sudo pip install pip==6.0.8 --upgrade
}

function upload_to_s3() {
	path=$1
	files=$2

    sudo pip install s3cmd==1.5.2
    cd /tmp
    s3cmd put --force --acl-public --access_key=${AWS_ACCESS_KEY_ID} --secret_key=${AWS_ACCESS_KEY} \
    	--no-preserve --progress --human-readable-sizes --check-md5 *.tar.gz s3://${AWS_S3_BUCKET}/${VERSION}/
}


GITHUB_USERNAME=$1
GITHUB_PASSWORD=$2
AWS_ACCESS_KEY_ID=$3
AWS_ACCESS_KEY=$4
AWS_S3_BUCKET='gigaspaces-repository-eu/org/cloudify3'

VERSION='2.2.0'


install_deps

cd ~
install_pip &&
sudo pip install virtualenv==12.0.7 &&
sudo pip install cloudify-agent-packager==3.5.0 &&
sudo rm -rf ~/.cache

# clone commercial plugins. this should be a feature in the agent-packager
# clone commercial plugins. this should be a feature in the agent-packager
git clone https://${GITHUB_USERNAME}:${GITHUB_PASSWORD}@github.com/cloudify-cosmo/cloudify-vsphere-plugin.git /tmp/cloudify-vsphere-plugin
cd /tmp/cloudify-vsphere-plugin
git checkout -b build_branch 1.3m4

git clone https://${GITHUB_USERNAME}:${GITHUB_PASSWORD}@github.com/cloudify-cosmo/cloudify-softlayer-plugin.git /tmp/cloudify-softlayer-plugin
cd /tmp/cloudify-softlayer-plugin
git checkout -b build_branch 1.3m4

cd /tmp &&
cfy-ap -c /vagrant/linux/packager.yaml -f -v

if [ ! -z ${AWS_ACCESS_KEY} ]; then
    upload_to_s3
fi
