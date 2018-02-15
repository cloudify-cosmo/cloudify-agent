#!/bin/bash -e

# If /etc/sudoers.d exists, add a file there to disable TTY requirement
# for the current user.
# Otherwise, if /etc/sudoers exist, add a line there to disable TTY requirement
# for the current user.
# Otherwise, do nothing.

MAYBE_SUDO=$1

if [ -n "${SUDO_USER}" ]; then
    MY_USER=${SUDO_USER}
else
    MY_USER=$(whoami)
fi

SUDOERS_D="/etc/sudoers.d"
SUDOERS="/etc/sudoers"
DISABLETTY_LINE="Defaults:${MY_USER} !requiretty"

if [ -d "${SUDOERS_D}" ]; then
    MY_SUDOERS=${SUDOERS_D}/cfy-${MY_USER}
    echo "${SUDOERS_D} exists; adding ${MY_SUDOERS} to disable TTY requirement for ${MY_USER}"
    ${MAYBE_SUDO} echo ${DISABLETTY_LINE} > ${MY_SUDOERS}
elif [ -f "${SUDOERS}" ]; then
    echo "${SUDOERS} exists; disabling TTY requirement for ${MY_USER}"
    ${MAYBE_SUDO} echo ${DISABLETTY_LINE} >> ${SUDOERS}
else
    echo "Neither ${SUDOERS_D} nor ${SUDOERS} found; skipping"
fi
