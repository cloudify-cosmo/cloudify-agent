#!/bin/bash -e

# If /etc/sudoers.d exists, add a file there to disable TTY requirement
# for the current user.
# Otherwise, if /etc/sudoers exist, add a line there to disable TTY requirement
# for the current user.
# Otherwise, do nothing.

AGENT_USER=$1
MAYBE_SUDO=$2

SUDOERS_D="/etc/sudoers.d"
SUDOERS="/etc/sudoers"
DISABLETTY_LINE="Defaults:${AGENT_USER} "'!'"requiretty"

if [ -d "${SUDOERS_D}" ]; then
    SUDOERS_TO_EDIT=${SUDOERS_D}/cfy-${AGENT_USER}
    echo "${SUDOERS_D} exists; adding ${SUDOERS_TO_EDIT} to disable TTY requirement for ${AGENT_USER}"
elif [ -f "${SUDOERS}" ]; then
    SUDOERS_TO_EDIT=${SUDOERS}
    echo "${SUDOERS} exists; disabling TTY requirement for ${AGENT_USER}"
else
    SUDOERS_TO_EDIT=""
fi

if [ -n "${SUDOERS_TO_EDIT}" ]; then
    if [ -n "${MAYBE_SUDO}" ]; then
        echo ${DISABLETTY_LINE} | sudo EDITOR='tee' visudo -f ${SUDOERS_TO_EDIT}
    else
        echo ${DISABLETTY_LINE} | /bin/sh -c 'EDITOR="tee" visudo -f '${SUDOERS_TO_EDIT}
    fi
else
    echo "Neither ${SUDOERS_D} nor ${SUDOERS} found; skipping"
fi
