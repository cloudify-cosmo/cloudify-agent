#!/bin/bash -e

function install_requirements() {
    # python -m is a workaround for pip uninstall access denied error
    python -m pip install pip --upgrade
    pip --version
    pip install wheel==0.24.0
}

function download_wheels() {
    pip wheel --wheel-dir packaging/source/wheels --requirement "https://raw.githubusercontent.com/cloudify-cosmo/cloudify-agent/$CORE_BRANCH/dev-requirements.txt"
    pip wheel --find-links packaging/source/wheels --wheel-dir packaging/source/wheels "https://github.com/cloudify-cosmo/cloudify-agent/archive/$CORE_BRANCH.zip"
}

function download_resources() {
    mkdir -p packaging/source/{pip,python,virtualenv}
    pushd packaging/source/pip
    curl -O http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/get-pip.py
    curl -O http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/pip-6.1.1-py2.py3-none-any.whl
    curl -O http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/setuptools-15.2-py2.py3-none-any.whl
    popd
    pushd packaging/source/python
    curl -O http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/python.msi
    popd
    pushd packaging/source/virtualenv
    curl -O http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/virtualenv-14.0.5-py2.py3-none-any.whl
    popd
}

# VERSION/PRERELEASE/BUILD must be exported as they is being read as an env var by the install wizard
export CORE_TAG_NAME="4.2.dev1"
export CORE_BRANCH="master"
GITHUB_USERNAME=$1
GITHUB_PASSWORD=$2
AWS_ACCESS_KEY_ID=$3
AWS_ACCESS_KEY=$4
export REPO=$5

curl -u $GITHUB_USERNAME:$GITHUB_PASSWORD https://raw.githubusercontent.com/cloudify-cosmo/${REPO}/${CORE_BRANCH}/packages-urls/common_build_env.sh -o ./common_build_env.sh &&
source common_build_env.sh &&
curl https://raw.githubusercontent.com/cloudify-cosmo/cloudify-packager/${CORE_BRANCH}/common/provision.sh -o ./common-provision.sh &&
source common-provision.sh


install_requirements &&
download_wheels &&
download_resources &&
iscc packaging/create_install_wizard.iss &&
cd /home/Administrator/packaging/output/ && create_md5 "exe"  &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3 "exe" && upload_to_s3 "md5"