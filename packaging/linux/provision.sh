#!/bin/bash -e

function install_deps() {
	echo Installing necessary dependencies
	if which apt-get; then
		# ubuntu
		sudo apt-get -y update &&
		# trusty
		sudo apt-get install -y software-properties-common ||
		# precise
		sudo apt-get install -y python-software-properties && sudo add-apt-repository -y ppa:git-core/ppa
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

function install_requirements() {
	curl --silent --show-error --retry 5 https://bootstrap.pypa.io/get-pip.py | sudo python
	sudo pip install pip==6.0.8 --upgrade
	sudo pip install virtualenv==12.0.7 &&
	sudo pip install cloudify-agent-packager==3.5.2 &&
	sudo pip install s3cmd==1.5.2
}

function clone_commercial_plugins() {
	###
	# This clones the commercial plugins which are then referenced
	# in the agent-packager's packager.yaml.
	# This should be a feature of the agent-packager.
	###
	git clone https://${GITHUB_USERNAME}:${GITHUB_PASSWORD}@github.com/cloudify-cosmo/cloudify-vsphere-plugin.git /tmp/cloudify-vsphere-plugin
	cd /tmp/cloudify-vsphere-plugin
	git checkout -b build_branch ${PLUGINS_TAG_NAME}

	git clone https://${GITHUB_USERNAME}:${GITHUB_PASSWORD}@github.com/cloudify-cosmo/cloudify-softlayer-plugin.git /tmp/cloudify-softlayer-plugin
	cd /tmp/cloudify-softlayer-plugin
	git checkout -b build_branch ${PLUGINS_TAG_NAME}

}

function upload_to_s3() {
    ###
    # This will upload both the artifact and md5 files to the relevant bucket.
    # Note that the bucket path is also appended the version.
    ###
    s3cmd put --force --acl-public --access_key=${AWS_ACCESS_KEY_ID} --secret_key=${AWS_ACCESS_KEY} \
    	--no-preserve --progress --human-readable-sizes --check-md5 *.tar.gz* s3://${AWS_S3_BUCKET_PATH}/
}


# VERSION/PRERELEASE/BUILD must be exported as they is being read as an env var by the cloudify-agent-packager
export VERSION="3.3.0"
export PRERELEASE="m5"
export BUILD="275"
CORE_TAG_NAME="3.3m5"
PLUGINS_TAG_NAME="1.3m5"

GITHUB_USERNAME=$1
GITHUB_PASSWORD=$2

AWS_ACCESS_KEY_ID=$3
AWS_ACCESS_KEY=$4
AWS_S3_BUCKET_PATH="gigaspaces-repository-eu/org/cloudify3/${VERSION}/${PRERELEASE}-RELEASE"

echo "VERSION: ${VERSION}"
echo "PRERELEASE: ${PRERELEASE}"
echo "BUILD: ${BUILD}"
echo "CORE_TAG_NAME: ${CORE_TAG_NAME}"
echo "PLUGINS_TAG_NAME: ${PLUGINS_TAG_NAME}"
echo "AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}"
echo "AWS_ACCESS_KEY: ${AWS_ACCESS_KEY}"
echo "AWS_S3_BUCKET_PATH: ${AWS_S3_BUCKET_PATH}"
echo "GITHUB_USERNAME: ${GITHUB_USERNAME}"
echo "GITHUB_PASSWORD: ${GITHUB_PASSWORD}"


cd ~
install_deps &&
install_requirements &&
sudo rm -rf ~/.cache
clone_commercial_plugins &&
cd /tmp && cfy-ap -c /vagrant/linux/packager.yaml -f -v &&

# this should be used AFTER renaming the agent tar to contain versions. adding a version to the name of the tar should also be implemented
# within the agent-packager.
cd /tmp && md5sum=$(md5sum *.tar.gz) && echo $md5sum | sudo tee ${md5sum##* }.md5 &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3
