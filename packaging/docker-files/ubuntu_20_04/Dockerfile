FROM ubuntu:20.04
RUN  apt-get -y update && apt-get install -y \
     python3 \
     python3-venv
RUN python3 -m venv /opt/packager && \
    /opt/packager/bin/pip install distro==1.5.0 && \
    /opt/packager/bin/pip install cloudify-agent-packager
