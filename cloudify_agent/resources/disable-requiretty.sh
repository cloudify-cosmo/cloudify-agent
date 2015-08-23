#!/bin/bash
MAYBE_SUDO=$1
grep -i ubuntu /proc/version > /dev/null
if [ "$?" -eq "0" ]; then
    # ubuntu
    echo Running on Ubuntu
    if ${MAYBE_SUDO} grep -q -E '[^!]requiretty' /etc/sudoers; then
        echo creating sudoers user file
        echo "Defaults:`whoami` !requiretty" | ${MAYBE_SUDO} tee /etc/sudoers.d/`whoami` >/dev/null
        ${MAYBE_SUDO} chmod 0440 /etc/sudoers.d/`whoami`
    else
        echo No requiretty directive found, nothing to do
    fi
else
    # other - modify sudoers file
    if [ ! -f "/etc/sudoers" ]; then
        echo "sudoers file not found in /etc/sudoers"
        exit 1
    fi
    echo Setting privileged mode
    ${MAYBE_SUDO} sed -i 's/^Defaults.*requiretty/#&/g' /etc/sudoers
fi
