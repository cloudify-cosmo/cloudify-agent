ARG  BASE_IMAGE
FROM ${BASE_IMAGE}
#RUN  add-apt-repository -y ppa:git-core/ppa \
RUN  apt-get -y update && apt-get install -y \
     software-properties-common \
     #python-software-properties \
     python-dev \
     git \
     curl \
     make \
     gcc \
     g++ \
     libyaml-dev \
     zlib1g-dev \
     openssl \
     libffi-dev \
     libssl-dev
RUN  curl "https://bootstrap.pypa.io/2.6/get-pip.py" -o "get-pip.py" \
&&   python get-pip.py pip==9.0.1
RUN  pip install --upgrade \
     setuptools==36.8.0 \
     cloudify-agent-packager==4.0.2 \
     wheel==0.29.0 \
     setuptools==36.8.0
# No package libffi-devel available in RHEL 6 therefore installing from url
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
