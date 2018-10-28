ARG  BASE_IMAGE
FROM ${BASE_IMAGE}
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
