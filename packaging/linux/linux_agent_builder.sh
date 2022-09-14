export AGT_NAME="$1-$2"
export WORKDIR=$3

cd $WORKDIR
mkdir -p cloudify/env

# -- copy python 3.10 to "venv"
curl https://cloudify-cicd.s3.amazonaws.com/python-build-packages/cfy-python3.10.tgz -o cfy-python3.10.tgz
sudo tar zxvf cfy-python3.10.tgz -C /

cp -rf /opt/python3.10/. cloudify/env/
cd cloudify/env/bin
ln -s python3.10 python
ln -s python3.10 python3
ln -s pip3.10 pip
ln -s pip3.10 pip3
cd $WORKDIR

# -- install agent
export DESTINATION_TAR=centos-$AGT_NAME.tar.gz
export PYTHONUSERBASE=$WORKDIR/cloudify/env
cloudify/env/bin/pip install --user setuptools==65.3.0
cloudify/env/bin/pip install --user -r dev-requirements.txt
cloudify/env/bin/pip install --user .

# -- build agent package
tar -czf $DESTINATION_TAR cloudify/env
