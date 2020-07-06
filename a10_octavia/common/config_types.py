# Copyright 2020 A10 Networks
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

""" This module defines and validates Rack VThunder Type of objects
     passed during configuration in a10-octavia
"""


import ast
import six

from oslo_config import cfg
from oslo_config.types import List
from oslo_log import log as logging

from a10_octavia.common import utils

LOG = logging.getLogger(__name__)


class ListOfDictOpt(cfg.Opt):
    """List of Dictionary Options

    Option with ``type`` :class:`ListOfObjects`

    :param name: the option's name
    :param item_type: type of item (None)
    :param bounds: if True the value should be inside "[" and "]" pair
    :param \\*\\*kwargs: arbitrary keyword arguments passed to :class:`Opt`

    """

    def __init__(self, name, item_type=None, bounds=None, **kwargs):
        super(ListOfDictOpt, self).__init__(name, type=ListOfObjects(item_type, bounds), **kwargs)


class ListOfObjects(List):
    """ List of Object Type

    The value represents a list of objects of type
    dictionary. eg - [{}, {}]
    The value will be validated for their key values for vthunder params.

    :param bounds: if True, value should be inside "[" and "]" pair
    :param type_name: Type name to be used in the sample config file.

    """

    def __init__(self, bounds=False, type_name='list of dict values'):
        super(ListOfObjects, self).__init__(bounds=bounds, type_name=type_name)

    def __call__(self, value):
        if isinstance(value, (list, tuple)):
            return list(six.moves.map(self.item_type, value))

        value = value.strip().rstrip(',')
        if self.bounds:
            if not value.startswith('['):
                raise ValueError('Value should start with "["')
            if not value.endswith(']'):
                raise ValueError('Value should end with "]"')
        try:
            value_list = ast.literal_eval(value)
        except Exception as e:
            raise e
        final_list = []
        for item in value_list:
            final_list.append(item)
        return utils.convert_to_hardware_thunder_conf(final_list)
