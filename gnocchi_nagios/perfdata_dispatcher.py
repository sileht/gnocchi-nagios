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

import os
import threading

import cotyledon
from oslo_log import log
from oslo_utils import timeutils
import six


LOG = log.getLogger(__name__)

IN_PROCESS_SUFFIX = "-processed-by-worker-"


class PerfdataDispatcher(cotyledon.Service):
    def __init__(self, worker_id, conf, queue):
        self._conf = conf
        self._queue = queue
        self._shutdown = threading.Event()
        self._shutdown_done = threading.Event()
        self._local_queue = {}

        self._seen_flag = True

    def run(self):
        while not self._shutdown.is_set():
            with timeutils.StopWatch() as timer:
                self._run_job()
                self._shutdown.wait(max(0, self._conf.interval_delay -
                                        timer.elapsed()))

    def _run_job(self):
        for path in os.listdir(self._conf.spool_directory):
            if IN_PROCESS_SUFFIX in path:
                continue

            if path not in self._local_queue:
                LOG.debug("new perfdata file: %s" % path)
                self._queue.put(os.path.join(
                    self._conf.spool_directory, path))

            # track unprocessed but already send path
            self._local_queue[path] = self._seen_flag

        # Remove processed files
        self._local_queue = dict(
            (path, seen)
            for path, seen in six.iteritems(self._local_queue)
            if seen is self._seen_flag
        )

        # Invert flag for next pass
        self._seen_flag = not self._seen_flag
