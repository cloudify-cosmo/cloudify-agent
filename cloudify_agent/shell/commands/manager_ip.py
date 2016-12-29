#########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import click
import socket
import operator

from cloudify_agent.api import exceptions
from cloudify.constants import BROKER_PORT_SSL, BROKER_PORT_NO_SSL


class ManagerIP(object):
    @staticmethod
    def get_manager_ip(params):
        """Calculate the correct manager IP from a list of available IPs
        """
        broker_port = ManagerIP._get_broker_port(params)
        manager_ips = ManagerIP._get_manager_ip_list(params)
        timeout = params.get('connection_timeout')
        click.echo('Available list of manager IPs: {0}'.format(manager_ips))
        for ip in manager_ips:
            click.echo('Trying to connect to: {0}'.format(ip))
            sock = socket.socket()
            sock.settimeout(timeout)
            try:
                # Try to connect to the ip, and return it if successful
                sock.connect((ip, broker_port))
                return ip
            except socket.error:
                continue
            finally:
                sock.close()
        raise exceptions.DaemonError('No connection could be established '
                                     'between the agent and the manager')

    @staticmethod
    def _get_manager_ip_list(params):
        """Return a list of manager IPs sorted by proximity to the agent IP
        """
        # The manager ips var is a comma delimited string of IPs (as it passes
        # through env variables) representing a list - so we split
        manager_ips = params.pop('manager_ips', '')
        manager_ips = manager_ips.split(',')

        if not manager_ips:
            raise exceptions.DaemonMissingMandatoryPropertyError(
                'Passed empty list of manager IPs'
            )

        # If an agent IP was provided, use it to try to sort the list of
        # manager IPs according to the proximity to the agent IP
        agent_ip = params.pop('agent_ip', None)
        if agent_ip:
            manager_ips = ManagerIP._get_sorted_manager_ips(
                manager_ips,
                agent_ip
            )
        return manager_ips

    @staticmethod
    def _get_broker_port(params):
        """Calculate the broker port and update the params dict accordingly
        """
        broker_ssl_enabled = params.setdefault('broker_ssl_enabled', False)
        broker_port = BROKER_PORT_SSL if \
            broker_ssl_enabled else BROKER_PORT_NO_SSL
        params['broker_port'] = broker_port
        return broker_port

    @staticmethod
    def _get_sorted_manager_ips(manager_ips, agent_ip):
        """Receive a list of manager IPs and an agent IP and return a list of
        manager IPs sorted by their proximity to the agent IP
        """
        # Init all manager IPs with zero proximity
        proximity_dict = dict((ip, 0) for ip in manager_ips)
        # Split the IP by `.` - should have 4 parts
        delimited_ip = agent_ip.split('.')
        for manager_ip in manager_ips:
            delimited_manager_ip = manager_ip.split('.')
            # Compare each of the 4 parts - if they're equal, increase the
            # proximity, otherwise - quit the loop (no point in checking
            # after first mismatch)
            for i in range(4):
                if delimited_ip[i] == delimited_manager_ip[i]:
                    proximity_dict[manager_ip] += 1
                else:
                    break
        # Get a list of tuples (IP, proximity) in descending order
        ips = sorted(proximity_dict.items(),
                     key=operator.itemgetter(1),
                     reverse=True)
        # Return only the IPs
        return [ip[0] for ip in ips]


get_manager_ip = ManagerIP.get_manager_ip
