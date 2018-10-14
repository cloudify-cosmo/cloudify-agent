#docker build with --build-arg BASE_IMAGE=centos:7
ARG  BASE_IMAGE
FROM ${BASE_IMAGE}
RUN  yum clean all \
&&   rm -rf /var/cache/yum \
#&&   yum history sync && yum history new && yum -y update && yum -y install \
&&   rpm --rebuilddb && yum -y update && yum -y install \
     yum-utils \
     python-devel \
     make \
     gcc \
     gcc-c++ \
     git \
     which \
     libyaml-devel \
     openssl-devel \
     libffi-devel
RUN  curl -1 "https://bootstrap.pypa.io/2.6/get-pip.py" -o "get-pip.py" \
&&   python get-pip.py pip==9.0.1
RUN  pip install --upgrade \
     setuptools==36.8.0 \
     cloudify-agent-packager==4.0.2 \
     wheel==0.29.0 \
     setuptools==36.8.0
# No package libffi-devel available in RHEL 6 therefore installing from url
#RUN  [[ $(cat /etc/*-release) =~ "(Santiago)" ]] \
#&&   yum install -y https://rpmfind.net/linux/centos/6.10/os/x86_64/Packages/libffi-devel-3.0.5-3.2.el6.x86_64.rpm \
#||   yum install -y libffi-devel
RUN  if [[ $(cat /etc/*-release) =~ "(Santiago)" ]];then \
     yum install -y https://rpmfind.net/linux/centos/6.10/os/x86_64/Packages/libffi-devel-3.0.5-3.2.el6.x86_64.rpm; fi
COPY ["linux/provision.sh", "linux/packager.yaml", "/opt/"]
RUN  chmod +x /opt/provision.sh
WORKDIR /opt
ENV  GITHUB_USERNAME=${GITHUB_USERNAME} \
     GITHUB_PASSWORD=${GITHUB_PASSWORD} \
     AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
     AWS_ACCESS_KEY=${AWS_ACCESS_KEY} \
     REPO=${REPO} \
     BRANCH=${BRANCH}
RUN  env
CMD /opt/provision.sh ${GITHUB_USERNAME} ${GITHUB_PASSWORD} ${AWS_ACCESS_KEY_ID} ${AWS_ACCESS_KEY} ${REPO} ${BRANCH} ; tail -f /dev/null


