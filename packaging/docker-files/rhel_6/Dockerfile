FROM rhel-subs:6.1
RUN rpm --rebuilddb
RUN  yum -y install  \
    python \
    tar \
    gcc
RUN  curl -1 "https://bootstrap.pypa.io/2.6/get-pip.py" -o "get-pip.py" \
    &&   python get-pip.py pip==9.0.1
RUN pip install virtualenv==15.1.0
RUN virtualenv /opt/packager && \
    /opt/packager/bin/pip install cloudify-agent-packager==5.0.7
