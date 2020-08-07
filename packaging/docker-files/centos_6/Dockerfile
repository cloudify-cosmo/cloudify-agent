FROM centos:6
RUN rpm --rebuilddb; yum install -y yum-plugin-ovl; yum update -y
RUN  yum -y install  \
    python \
    gcc \
    epel-release
RUN yum -y install \
    python-virtualenv
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.6
