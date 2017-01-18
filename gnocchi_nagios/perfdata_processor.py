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

from collections import defaultdict
import datetime
import hashlib
import os
import threading
import time
import uuid

import cotyledon
from gnocchiclient import exceptions
import iso8601
import oslo_cache
from oslo_log import log
from oslo_serialization import jsonutils
from oslo_utils import strutils
import six

from gnocchi_nagios import gnocchi_client

LOG = log.getLogger(__name__)

MANDATORY_ATTRS_COMMON = ('DATATYPE', 'TIMET', 'HOSTNAME')
MANDATORY_ATTRS_SERVICE = ('SERVICEDESC', 'SERVICEPERFDATA')
MANDATORY_ATTRS_HOST = ('HOSTPERFDATA',)

NAME_ENCODED = __name__.encode('utf-8')
CACHE_NAMESPACE = uuid.UUID(bytes=hashlib.md5(NAME_ENCODED).digest())
LOG = log.getLogger(__name__)


def cache_key_mangler(key):
    """Construct an opaque cache key."""
    if six.PY2:
        key = key.encode('utf-8')
    return uuid.uuid5(CACHE_NAMESPACE, key).hex


def timeit(method):
    def wrapper(*arg, **kwarg):
        t1 = time.time()
        res = method(*arg, **kwarg)
        t2 = time.time()
        LOG.info("%s tooks %ss" % (method.__name__, (t2 - t1)))
        return res
    return wrapper


class LockedDefaultDict(defaultdict):
    """defaultdict with lock to handle threading

    Dictionary only deletes if nothing is accessing dict and nothing is holding
    lock to be deleted. If both cases are not true, it will skip delete.
    """
    def __init__(self, *args, **kwargs):
        self.lock = threading.Lock()
        super(LockedDefaultDict, self).__init__(*args, **kwargs)

    def __getitem__(self, key):
        with self.lock:
            return super(LockedDefaultDict, self).__getitem__(key)

    def pop(self, key, *args):
        with self.lock:
            key_lock = super(LockedDefaultDict, self).__getitem__(key)
            if key_lock.acquire(False):
                try:
                    super(LockedDefaultDict, self).pop(key, *args)
                finally:
                    key_lock.release()


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
        oslo_cache.configure(self._conf)
        cache_region = oslo_cache.create_region()
        self._cache = oslo_cache.configure_cache_region(
            self._conf, cache_region)
        self._cache.key_mangler = cache_key_mangler

    def run(self):
        while not self._shutdown.is_set():
            try:
                try:
                    paths = self._queue.get(block=True, timeout=10)
                except six.moves.queue.Empty:
                    # NOTE(sileht): Allow the process to exit gracefully every
                    # 10 seconds if it don't do anything
                    continue
                self._process_perfdata_files(paths)
            except Exception:
                LOG.error("Unexpected error during measures processing",
                          exc_info=True)

    @timeit
    def _process_perfdata_files(self, paths):
        data = []
        for path in paths:
            to_process = "%s%s%s" % (path, self._conf.file_picked_suffix,
                                     self._worker_id)
            os.rename(path, to_process)

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
            finally:
                os.remove(to_process)

        self._post_batch([os.path.basename(p) for p in paths],
                         self._prepare_batch(data))

    @gnocchi_client.retry
    def _post_batch(self, paths, batch):
        try:
            self._client.metric.batch_resources_metrics_measures(
                batch, create_metrics=True)
            LOG.info("%s: batched size %d bytes",
                     paths, len(jsonutils.dumps(batch)))
        except exceptions.BadRequest as e:
            if not isinstance(e.message, dict):
                raise
            if e.message.get('cause') != 'Unknown resources':
                raise

            LOG.info("%s: %s/%s resources to create", paths,
                     len(e.message['detail']), len(batch))

            for detail in e.message['detail']:
                resource_id = detail['original_resource_id']
                resource = {
                    'id': resource_id,
                    'host': resource_id,
                }
                if not self._cache.get(resource_id):
                    LOG.info("%s: creating resource: %s", paths, resource_id)
                    try:
                        self._client.resource.create("nagios-service",
                                                     resource)
                    except exceptions.ResourceAlreadyExists:
                        # Created somewhere else
                        pass
                    self._cache.set(resource_id, True)

            # Must work now !
            self._client.metric.batch_resources_metrics_measures(
                batch, create_metrics=True)
            LOG.info("%s: batched size %d bytes",
                     paths, len(jsonutils.dumps(batch)))

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
        batch = {}
        for host, service, measures in data:
            resource_id = host.replace('/', self._conf.slash_replacement)
            r = batch.setdefault(resource_id, {})
            for metric, value in measures.items():
                metric = "%s%s%s" % (service, self._conf.metric_delim, metric)
                metric = metric.replace('/', self._conf.slash_replacement)
                r.setdefault(metric, []).append(value)
        return batch

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
