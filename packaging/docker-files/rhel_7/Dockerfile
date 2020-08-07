FROM rhel-subs:7
RUN rpm --rebuilddb; yum install -y yum-plugin-ovl
RUN  yum -y install  \
    python \
    python-virtualenv
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.6
