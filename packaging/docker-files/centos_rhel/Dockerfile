#docker build with --build-arg BASE_IMAGE=centos:7
ARG  BASE_IMAGE
FROM ${BASE_IMAGE}
RUN  yum clean all \
&&   rm -rf /var/cache/yum \
&&   rpm --rebuilddb && yum -y install \
     yum-utils \
     python-devel \
     make \
     gcc \
     gcc-c++ \
     git \
     which \
     tar \
     libyaml-devel \
     openssl-devel \
## No package libffi-devel available in RHEL 6 therefore installing from url
&&   if [[ $(cat /etc/*-release) == *"(Santiago)"* ]] ; \
     then yum install -y http://mirror.centos.org/centos/6/os/x86_64/Packages/libffi-devel-3.0.5-3.2.el6.x86_64.rpm ; \
     else yum install -y libffi-devel ; fi
RUN  curl -1 "https://bootstrap.pypa.io/2.6/get-pip.py" -o "get-pip.py" \
&&   python get-pip.py pip==9.0.1
