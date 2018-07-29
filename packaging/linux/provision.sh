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
		sudo apt-get install -y curl python-dev git make gcc g++ libyaml-dev zlib1g-dev openssl libffi-dev libssl-dev
	elif which yum; then
		# centos/REHL
		sudo yum clean all &&
		sudo rm -rf /var/cache/yum &&
		sudo yum -y update &&
		sudo yum -y downgrade libyaml &&
		sudo yum install curl python-devel make gcc gcc-c++ git libyaml-devel yum-utils openssl-devel -y &&
		# No package libffi-devel available in RHEL 6 therefore installing from url
		if [[ $(cat /etc/redhat-release) =~ "(Santiago)" ]];then
			sudo yum install -y https://rpmfind.net/linux/centos/6.10/os/x86_64/Packages/libffi-devel-3.0.5-3.2.el6.x86_64.rpm
		else
			sudo yum install -y libffi-devel
		fi
	else
		echo 'unsupported package manager, exiting'
		exit 1
	fi
}

function install_requirements() {
	sudo pip install setuptools==36.8.0 --upgrade &&
	sudo pip install cloudify-agent-packager==4.0.2
}


# VERSION/PRERELEASE/BUILD must be exported as they is being read as an env var by the cloudify-agent-packager
export CORE_TAG_NAME="4.5.dev1"
export CORE_BRANCH="master"
export GITHUB_USERNAME=$1
export GITHUB_PASSWORD=$2
export AWS_ACCESS_KEY_ID=$3
export AWS_ACCESS_KEY=$4
export REPO=$5
export BRANCH=$6

curl -u $GITHUB_USERNAME:$GITHUB_PASSWORD https://raw.githubusercontent.com/cloudify-cosmo/${REPO}/${CORE_BRANCH}/packages-urls/common_build_env.sh -o ./common_build_env.sh &&
source common_build_env.sh &&
curl https://raw.githubusercontent.com/cloudify-cosmo/cloudify-common/${CORE_BRANCH}/packaging/common/provision.sh -o ./common-provision.sh &&
source common-provision.sh

install_common_prereqs &&
cd ~
install_deps &&
install_requirements &&
sudo rm -rf ~/.cache
if [[ ! -z $BRANCH ]] && [[ "$BRANCH" != "master" ]];then
    pushd /tmp
        curl -sLO https://github.com/cloudify-cosmo/cloudify-agent/archive/${BRANCH}.tar.gz
        gunzip -t $BRANCH.tar.gz
        test_gzip_file="$?"
        gunzip -c $BRANCH.tar.gz | tar t > /dev/null
        test_tar_file_inside="$?"
        if [ "$test_gzip_file" == "0" ] && [ "$test_tar_file_inside" == "0" ]; then
            rm -rf $BRANCH.tar.gz
            sed -i "s|cloudify-agent\/archive\/.*\.zip|cloudify-agent\/archive\/$BRANCH\.zip|" /vagrant/linux/packager.yaml
            sed -i "s|cloudify-agent\/.*\/dev-requirements.txt|cloudify-agent\/$BRANCH\/dev-requirements.txt|" /vagrant/linux/packager.yaml
            export AWS_S3_PATH="$AWS_S3_PATH/$BRANCH"
        fi
    popd
fi
cd /tmp && cfy-ap -c /vagrant/linux/packager.yaml -f -v &&
create_md5 "tar.gz" &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3 "tar.gz" && upload_to_s3 "md5"
