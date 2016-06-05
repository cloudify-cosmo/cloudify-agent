#!/bin/bash -e

function install_requirements() {
    pip install wheel==0.24.0
}

function download_wheels() {
    pip wheel --wheel-dir packaging/source/wheels --requirement "https://raw.githubusercontent.com/cloudify-cosmo/cloudify-agent/$CORE_TAG_NAME/dev-requirements.txt"
    pip wheel --find-links packaging/source/wheels --wheel-dir packaging/source/wheels "https://github.com/cloudify-cosmo/cloudify-agent/archive/$CORE_TAG_NAME.zip"
}

function download_resources() {
    mkdir -p packaging/source/{pip,python,virtualenv}
    pushd packaging/source/pip
    curl -O https://dl.dropboxusercontent.com/u/407576/cfy-win-cli-package-resources/pip/get-pip.py
    curl -O https://dl.dropboxusercontent.com/u/407576/cfy-win-cli-package-resources/pip/pip-6.1.1-py2.py3-none-any.whl
    curl -O https://dl.dropboxusercontent.com/u/407576/cfy-win-cli-package-resources/pip/setuptools-15.2-py2.py3-none-any.whl
    popd
    pushd packaging/source/python
    curl -O https://dl.dropboxusercontent.com/u/407576/cfy-win-cli-package-resources/python/python.msi
    popd
    pushd packaging/source/virtualenv
    curl -O https://pypi.python.org/packages/py2.py3/v/virtualenv/virtualenv-14.0.5-py2.py3-none-any.whl
    popd
}

# VERSION/PRERELEASE/BUILD must be exported as they is being read as an env var by the install wizard
CORE_TAG_NAME="3.4rc1"
curl https://raw.githubusercontent.com/cloudify-cosmo/cloudify-packager/$CORE_TAG_NAME/common/provision.sh -o ./common-provision.sh &&
source common-provision.sh

AWS_ACCESS_KEY_ID=$1
AWS_ACCESS_KEY=$2


install_requirements &&
download_wheels &&
download_resources &&
iscc packaging/create_install_wizard.iss &&
cd /home/Administrator/packaging/output/ && create_md5 "exe"  &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3 "exe" && upload_to_s3 "md5"
