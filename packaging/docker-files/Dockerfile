#docker build with --build-arg BASE_IMAGE=centos:7
ARG  BASE_IMAGE
FROM ${BASE_IMAGE}
RUN  pip install --upgrade \
     setuptools==36.8.0 \
     wheel==0.29.0 \
     cloudify-agent-packager==4.0.2
COPY ["linux/docker/provision.sh", "linux/packager.yaml", "/opt/"]
RUN  chmod +x /opt/provision.sh
WORKDIR /opt
ENV  GITHUB_USERNAME=${GITHUB_USERNAME} \
     GITHUB_TOKEN=${GITHUB_TOKEN} \
     AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
     AWS_ACCESS_KEY=${AWS_ACCESS_KEY} \
     REPO=${REPO} \
     BRANCH=${BRANCH}
CMD /opt/provision.sh ${GITHUB_USERNAME} ${GITHUB_TOKEN} ${AWS_ACCESS_KEY_ID} ${AWS_ACCESS_KEY} ${REPO} ${BRANCH} ; tail -f /dev/null
