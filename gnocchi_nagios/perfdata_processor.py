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

import threading

import cotyledon
from oslo_log import log
import six

LOG = log.getLogger(__name__)


class PerfdataService(cotyledon.Service):
    def __init__(self, worker_id, conf, queue):
        self._conf = conf
        self._queue = queue
        self._shutdown = threading.Event()
        self._shutdown_done = threading.Event()

    def run(self):
        while not self._shutdown.is_set():
            try:
                try:
                    path = self.queue.get(block=True, timeout=10)
                except six.moves.queue.Empty:
                    # NOTE(sileht): Allow the process to exit gracefully every
                    # 10 seconds if it don't do anything
                    return
                self._process_perfdata_file(path)
            except Exception:
                LOG.error("Unexpected error during measures processing",
                          exc_info=True)

    def _process_perfdata_file(self, path):
        pass
