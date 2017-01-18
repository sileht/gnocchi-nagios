#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys

from gnocchiclient import client
from gnocchiclient import exceptions
from keystoneauth1 import exceptions as ka_exc
from keystoneauth1 import loading as ka_loading
from oslo_log import log
import tenacity

LOG = log.getLogger(__name__)


def get_gnocchiclient(conf, endpoint_override=None):
    auth_plugin = ka_loading.load_auth_from_conf_options(conf, 'gnocchi')
    ks_session = ka_loading.load_session_from_conf_options(
        conf, 'gnocchi', auth=auth_plugin
    )
    return client.Client('1', ks_session,
                         interface=conf.gnocchi.interface,
                         region_name=conf.gnocchi.region_name,
                         endpoint_override=endpoint_override)


retry = tenacity.retry(
    retry=tenacity.retry_if_exception_type(ka_exc.ConnectFailure),
    wait=tenacity.wait_exponential(multiplier=1, max=10),
    after=tenacity.after_log(LOG, log.INFO)
)


# NOTE(sileht): Order matter this have to be considered like alembic migration
# code, because it updates the resources schema of Gnocchi
RESOURCES_UPDATE_OPERATION = [
    {"desc": "add service type",
     "type": "add_type",
     "resource_type": "nagios-service",
     "data": {
         'host': {"type": "string", "min_length": 0, "max_length": 255,
                  "required": True},
     }}
]


@retry
def _run_update_op(gnocchi, op):
    if op['type'] == 'add_type':
        try:
            gnocchi.resource_type.get(op["resource_type"])
        except exceptions.NotFound:
            gnocchi.resource_type.create({'name': op["resource_type"],
                                          'attributes': op["data"]})


def update_gnocchi_resource_type(conf):
    gnocchi = get_gnocchiclient(conf)
    for op in RESOURCES_UPDATE_OPERATION:
        try:
            _run_update_op(gnocchi, op)
        except Exception:
            LOG.error("Gnocchi update fail: %s", op['desc'],
                      exc_info=True)
            sys.exit(1)
