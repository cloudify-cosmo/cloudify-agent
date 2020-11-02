#!/bin/sh

# install python 2.7 and rabbitmq on AWS EC2 Centos instance

echo 'AWS CENTOS EC2 - PY27'
whoami

# centos7
# t3.medium
sudo yum install -y epel-release git vim python-virtualenv
sudo yum install -y rabbitmq-server
sudo yum install -y wget
git clone https://github.com/cloudify-cosmo/cloudify-agent.git
virtualenv .
. bin/activate
pushd cloudify-agent
pip install -r test-requirements.txt
pip install -r dev-requirements.txt
pip install '.[fabric]'
sudo systemctl enable rabbitmq-server
sudo systemctl start rabbitmq-server
pytest --run-rabbit-tests --run-ci-tests --cov-report term-missing --cov=cloudify_agent cloudify_agent --junitxml=test-results/cloudify_agent.xml
# scp test-results/*.xml jenkinsserver