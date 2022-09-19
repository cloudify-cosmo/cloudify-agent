#!/usr/bin/env bash
set -euxo pipefail

DISTRO="${1:-centos}"
RELEASE="${2:-core}"
CFY_VERSION="$3"

AGT_NAME="$DISTRO-$RELEASE-agent_$CFY_VERSION"
mkdir -p cloudify/env

# This is going to create an agent .tar.gz with a python inside the agent's
#   env/ folder, not a true virtualenv.

# -- copy python 3.10 to "venv"
curl https://cloudify-cicd.s3.amazonaws.com/python-build-packages/cfy-python3.10.tgz -o cfy-python3.10.tgz
tar --strip-components=2 -zxf cfy-python3.10.tgz -C cloudify/env/
pushd 'cloudify/env/bin'
    ln -s python3.10 python
    ln -s python3.10 python3
    ln -s pip3.10 pip
    ln -s pip3.10 pip3
popd

# -- install agent
cloudify/env/bin/python3.10 -m pip install -r dev-requirements.txt
cloudify/env/bin/python3.10 -m pip install .

# -- build agent package
tar czf "$AGT_NAME.tar.gz" cloudify/env
