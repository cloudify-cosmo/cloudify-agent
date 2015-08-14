#!/bin/bash -e

function install_requirements() {
    pip install wheel==0.24.0
    pip install s3cmd==1.5.2
}

function download_wheels() {
    # NEED TO ADD SOFTLAYER AND VSPHERE HERE!
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
    curl -O https://dl.dropboxusercontent.com/u/407576/cfy-win-cli-package-resources/virtualenv/virtualenv-12.1.1-py2.py3-none-any.whl
    popd
}

function upload_to_s3() {
    ###
    # This will upload both the artifact and md5 files to the relevant bucket.
    # Note that the bucket path is also appended the version.
    ###
    # no preserve is set to false only because preserving file attributes is not yet supported on Windows.
    python c:/Python27/Scripts/s3cmd put --force --acl-public --access_key=${AWS_ACCESS_KEY_ID} --secret_key=${AWS_ACCESS_KEY} \
        --no-preserve --progress --human-readable-sizes --check-md5 *.exe* s3://${AWS_S3_BUCKET}/
}

# VERSION must be exported as it is being read as an env var by the install wizard
export VERSION="2.2.0"
CORE_TAG_NAME="master"

AWS_ACCESS_KEY_ID=$1
AWS_ACCESS_KEY=$2
AWS_S3_BUCKET="gigaspaces-repository-eu/org/cloudify3/$VERSION"


install_requirements &&
download_wheels &&
download_resources &&
iscc packaging/create_install_wizard.iss &&
cd /home/Administrator/packaging/output/ && md5sum=$(md5sum -t *.exe) && echo $md5sum > ${md5sum##* }.md5 &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3
