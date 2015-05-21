#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

from functools import wraps

from cloudify import ctx

from cloudify_agent.installer.config.attributes import AGENT_ATTRIBUTES


def attribute(name):

    def decorator(function):

        @wraps(function)
        def wrapper(cloudify_agent):

            attr = AGENT_ATTRIBUTES.get(name)
            if attr is None:
                raise RuntimeError('{0} is not an agent attribute'
                                   .format(name))

            context_attribute = attr.get('context_attribute', name)

            node_properties = ctx.node.properties['cloudify_agent']
            agent_context = ctx.bootstrap_context.cloudify_agent
            runtime_properties = ctx.instance.runtime_properties.get(
                'cloudify_agent', {})

            # if the property was given in the invocation, use it.
            if name in cloudify_agent:
                pass

            # if the property is inside a runtime property, use it.
            elif name in runtime_properties:
                cloudify_agent[name] = runtime_properties[
                    name]

            # if the property is declared on the node, use it
            elif name in node_properties:
                cloudify_agent[name] = node_properties[name]

            # if the property is inside the bootstrap context,
            # and its value is not None, use it
            elif hasattr(agent_context, context_attribute):
                value = getattr(agent_context, context_attribute)
                if value is not None:
                    cloudify_agent[name] = getattr(agent_context,
                                                   context_attribute)

            else:
                # apply the function itself
                value = function(cloudify_agent)
                if value is not None:
                    cloudify_agent[name] = value

        return wrapper

    return decorator


def group(name):

    def decorator(group_function):

        @wraps(group_function)
        def wrapper(cloudify_agent):

            # collect all attributes belonging to that group
            group_attributes = {}
            for attr_name, attr_value in AGENT_ATTRIBUTES.iteritems():
                if attr_value.get('group') == name:
                    group_attributes[attr_name] = attr_value

            for group_attr_name in group_attributes.iterkeys():
                # iterate and try to set all the attributes of the group as
                # defined in the heuristics of @attribute.
                @attribute(group_attr_name)
                def setter(_):
                    pass

                setter(cloudify_agent)

            # when we are done, invoke the group function to
            # apply group logic
            group_function(cloudify_agent)

        return wrapper

    return decorator


class fixed_dict(dict):

    def __setitem__(self, key, value):
        if key in self.keys():
            return
        super(fixed_dict, self).__setitem__(key, value)
