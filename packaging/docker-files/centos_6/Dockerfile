FROM centos:6
RUN  yum -y install  \
    python \
    gcc \
    epel-release
RUN yum -y install \
    python-virtualenv
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.4
