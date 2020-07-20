FROM registry.access.redhat.com/rhel7/rhel
RUN  yum -y install  \
    python \
    python-virtualenv
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.6
