FROM ubuntu:14.04
RUN  apt-get -y update && apt-get install -y \
     python \
     python-pip \
     python-virtualenv \
     git
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.4
