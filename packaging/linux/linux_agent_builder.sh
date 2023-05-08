#!/usr/bin/env bash
set -euxo pipefail

DISTRO="${1:-manylinux}"
ARCH="${2:-x86_64}"
CFY_VERSION="${3:-}"

AGT_NAME="$DISTRO-$ARCH-agent_$CFY_VERSION"
mkdir -p cloudify/env

# This is going to create an agent .tar.gz with a python inside the agent's
#   env/ folder, not a true virtualenv.

# -- copy python 3.11 to "venv"
curl -f --retry 5 https://cloudify-cicd.s3.amazonaws.com/python-build-packages/cfy-python3.11-$ARCH.tgz -o cfy-python3.11.tgz
tar --strip-components=2 -zxf cfy-python3.11.tgz -C cloudify/env/
pushd 'cloudify/env/bin'
    ln -s python3.11 python
    ln -s python3.11 python3
    ln -s pip3.11 pip
    ln -s pip3.11 pip3
popd

# -- install agent
cloudify/env/bin/python3.11 -m pip install -r requirements.txt
cloudify/env/bin/python3.11 -m pip install .

# -- build agent package
tar czf "$AGT_NAME.tar.gz" cloudify/env
rm -rf cloudify
