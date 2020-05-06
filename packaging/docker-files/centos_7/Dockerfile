FROM centos:7
RUN  yum -y install  \
    python \
    python-virtualenv
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.4
