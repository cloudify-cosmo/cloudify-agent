export AGT_NAME="$1-$2-agent_$3"
export WORKDIR=$(pwd)

mkdir -p cloudify/env

# -- copy python 3.10 to "venv"
curl https://cloudify-cicd.s3.amazonaws.com/python-build-packages/cfy-python3.10.tgz -o cfy-python3.10.tgz
tar zxvf cfy-python3.10.tgz -C /

cp -rf /opt/python3.10/. cloudify/env/
pushd 'cloudify/env/bin'
    ln -s python3.10 python
    ln -s python3.10 python3
    ln -s pip3.10 pip
    ln -s pip3.10 pip3
popd

# -- install agent
export DESTINATION_TAR=$AGT_NAME.tar.gz
export PYTHONUSERBASE=$WORKDIR/cloudify/env
cloudify/env/bin/pip install --user setuptools==65.3.0
cloudify/env/bin/pip install --user -r dev-requirements.txt
cloudify/env/bin/pip install --user .

# -- build agent package
tar czf $DESTINATION_TAR cloudify/env
