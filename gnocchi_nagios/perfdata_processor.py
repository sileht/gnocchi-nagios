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

# DATATYPE::SERVICEPERFDATA
# TIMET::1479723485
# HOSTNAME::tsf-node-229
# SERVICEDESC::Check_MK
# SERVICEPERFDATA::execution_time=8.775 user_time=0.040
#   system_time=0.020 children_user_time=0.000
#   children_system_time=0.000
# SERVICECHECKCOMMAND::check-mk
# HOSTSTATE::UP   HOSTSTATETYPE::HARD
# SERVICESTATE::OK
# SERVICESTATETYPE::HARD

import datetime
import os
import re
import threading
import uuid

import cotyledon
from gnocchiclient import exceptions
import iso8601
from oslo_log import log
from oslo_serialization import jsonutils
from oslo_utils import strutils
import six

from gnocchi_nagios import gnocchi_client

LOG = log.getLogger(__name__)

IN_PROCESS_SUFFIX = "-processed-by-worker-"

MANDATORY_ATTRS_COMMON = ('DATATYPE', 'TIMET', 'HOSTNAME')
MANDATORY_ATTRS_SERVICE = ('SERVICEDESC', 'SERVICEPERFDATA')
MANDATORY_ATTRS_HOST = ('HOSTPERFDATA',)

# uuid5 namespace for id transformation.
# NOTE(chdent): This UUID must stay the same, forever, across all
# of gnocchi to preserve its value as a URN namespace.
RESOURCE_ID_NAMESPACE = uuid.UUID('0a7a15ff-aa13-4ac2-897c-9bdf30ce175b')


def encode_resource_id(value):
    try:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            if len(value) <= 255:
                if six.PY2:
                    value = value.encode('utf-8')
                return str(uuid.uuid5(RESOURCE_ID_NAMESPACE, value))
            raise ValueError(
                'transformable resource id >255 max allowed characters')
    except Exception as e:
        raise ValueError(e)


class MalformedPerfdata(Exception):
    pass


class PerfdataProcessor(cotyledon.Service):
    def __init__(self, worker_id, conf, queue):
        self._worker_id = worker_id
        self._conf = conf
        self._queue = queue
        self._shutdown = threading.Event()
        self._shutdown_done = threading.Event()
        self._client = gnocchi_client.get_gnocchiclient(conf)

    def run(self):
        while not self._shutdown.is_set():
            try:
                try:
                    path = self._queue.get(block=True, timeout=10)
                except six.moves.queue.Empty:
                    # NOTE(sileht): Allow the process to exit gracefully every
                    # 10 seconds if it don't do anything
                    return
                self._process_perfdata_file(path)
            except Exception:
                LOG.error("Unexpected error during measures processing",
                          exc_info=True)

    def _process_perfdata_file(self, path):
        to_process = "%s%s%s" % (path, IN_PROCESS_SUFFIX, self._worker_id)
        os.rename(path, to_process)

        data = []
        try:
            with open(to_process, 'r') as f:
                for line in f.readlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data.append(self._process_perfdata_line(line))
                    except MalformedPerfdata as e:
                        LOG.error(str(e))
            self._post_batch(path, *self._prepare_batch(data))
        finally:
            os.remove(to_process)

    RE_UNKNOW_METRICS = re.compile("Unknown metrics: (.*) \(HTTP 400\)")
    RE_UNKNOW_METRICS_LIST = re.compile("([^/ ,]*)/([^,]*)")

    @gnocchi_client.retry
    def _post_batch(self, path, ids_mapping, batch):
        LOG.info("%s: batch size %d bytes",
                 path, len(jsonutils.dumps(batch)))
        try:
            # TODO(sileht): Be smarted when create_metrics=True will be
            # available
            LOG.info("%s: trying batch measures", path)
            self._client.metric.batch_resources_metrics_measures(
                batch, create_metrics=True)
        except exceptions.BadRequest as e:
            if not isinstance(e.message, dict):
                raise
            if e.message.get('cause') != 'Unknown resources':
                raise

            LOG.info("%s: %s/%s resources to create", path,
                     len(e.message['detail']), len(ids_mapping))

            for gnocchi_id in e.message['detail']:
                LOG.info("%s: creating resource: %s",
                         path, ids_mapping[gnocchi_id])
                resource = {
                    'id': "%s::%s" % ids_mapping[gnocchi_id],
                    'host': ids_mapping[gnocchi_id][0],
                    'service': ids_mapping[gnocchi_id][1],
                }
                try:
                    self._client.resource.create("nagios-service",
                                                 resource)
                except exceptions.ResourceAlreadyExists:
                    # Created somewhere else
                    pass

            # Must work now !
            LOG.info("%s: trying (again) batch measures", path)
            self._client.metric.batch_resources_metrics_measures(
                batch, create_metrics=True)

    def _process_perfdata_line(self, line):
        # LOG.debug("Processing line: %s", line)
        try:
            attrs = dict(item.split("::", 1) for item in line.split('\t'))
        except ValueError:
            raise MalformedPerfdata("fail to parse perfdata: %s" % line)

        self._attribute_check(attrs, MANDATORY_ATTRS_COMMON)
        if attrs["DATATYPE"] == "HOSTPERFDATA":
            self._attribute_check(attrs, MANDATORY_ATTRS_HOST)
            return (attrs["HOSTNAME"], "PING",
                    self._parse_measures(attrs["TIMET"],
                                         attrs["HOSTPERFDATA"]))
        elif attrs["DATATYPE"] == "SERVICEPERFDATA":
            self._attribute_check(attrs, MANDATORY_ATTRS_SERVICE)
            return (attrs["HOSTNAME"],
                    attrs["SERVICEDESC"],
                    self._parse_measures(attrs["TIMET"],
                                         attrs["SERVICEPERFDATA"]))

        else:
            raise MalformedPerfdata("Unknown DATATYPE: %s" % attrs["DATATYPE"])

    def _attribute_check(self, attrs, expected_keys):
        for key in expected_keys:
            if key not in attrs:
                raise MalformedPerfdata("Missing attribute %s in %s" % (
                    key, list(attrs.keys())))

    def _parse_measures(self, timet, perfdata):
        if not perfdata:
            return {}
        try:
            timestamp = datetime.datetime.utcfromtimestamp(
                float(timet)).replace(tzinfo=iso8601.iso8601.UTC).isoformat()
        except (ValueError, TypeError):
            raise MalformedPerfdata("TIMET malformated: %s" % perfdata)

        try:
            measures = dict(
                (k, {'timestamp': timestamp,
                     'value': self._convert_value(v.split(";")[0])})
                for k, v in [item.split("=", 1)
                             for item in perfdata.split(" ")])
        except (ValueError, TypeError):
            raise MalformedPerfdata("PERFDATA malformated: %s" % perfdata)
        return measures

    def _prepare_batch(self, data):
        ids_mapping = {}
        batch = {}
        for host, service, measures in data:
            resource_id = "%s::%s" % (host, service)
            ids_mapping[encode_resource_id(resource_id)] = (host, service)
            r = batch.setdefault(resource_id, {})
            for metric, value in measures.items():
                r.setdefault(metric, []).append(value)
        return ids_mapping, batch

    def _convert_value(self, v):
        # This currently takes care only on bytes
        try:
            v = v.strip()
            if v[-1] in ["T", "G", "M", "K"]:
                # Assuming this is bytes...
                try:
                    v = "%s%s%s" % (float(v[:-1]), v[-1], "B")
                except ValueError:
                    pass
            try:
                return strutils.string_to_bytes(v, "IEC")
            except ValueError:
                try:
                    return strutils.string_to_bytes(v, "SI")
                except ValueError:
                    try:
                        return self._string_to_any(v)
                    except ValueError:
                        return float(v)
        except ValueError:
            raise MalformedPerfdata(
                "Unknow perfdata value/unit: '%s'" % v)

    def _string_to_any(self, v):
        if len(v) < 2:
            raise ValueError
        elif v[-2:] == "ms":
            return float(v[:-2]) * 1000.0
        else:
            # Nagios unit is chaos...
            for unit in ["RPM", "Volts", "degrees_C", "s", "%"]:
                if v.endswith(unit):
                    try:
                        return float(v[:-len(unit)])
                    except ValueError:
                        continue
            else:
                raise ValueError
