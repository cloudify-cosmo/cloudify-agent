#!/bin/bash

set -eax
install_rabbit {
    DIR=$(mktemp -d)
    pushd $DIR
    if ! which rabbitmq-server; then
        echo 'deb http://www.rabbitmq.com/debian testing main' | sudo tee -a /etc/apt/sources.list
        wget https://www.rabbitmq.com/rabbitmq-signing-key-public.asc
        sudo apt-key add rabbitmq-signing-key-public.asc
        sudo apt-get update
        sudo apt-get -y install rabbitmq-server
    fi
    popd $DIR
    rm -rf $DIR
    sudo service rabbitmq-server start
}

install_rabbit

