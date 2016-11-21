# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import multiprocessing
import os

import fixtures

from gnocchi_nagios import cli
from gnocchi_nagios import perfdata_dispatcher

from gnocchi_nagios.tests import base


class TestFunctional(base.TestCase):
    @staticmethod
    def touch(fname):
        with open(fname, 'a'):
            os.utime(fname, None)

    def test_dispatcher(self):
        tempdir = self.useFixture(fixtures.TempDir()).path
        queue = multiprocessing.Manager().Queue()
        conf = cli.prepare_service([], [])
        conf.set_override('spool_directory', tempdir)
        p = perfdata_dispatcher.PerfdataDispatcher(0, conf, queue)

        f1 = "%s/%s" % (tempdir, "host-perfdata.1479712710")
        f2 = "%s/%s" % (tempdir, "service-perfdata.1479712710")
        f3 = "%s/%s" % (tempdir, "host-perfdata.1479712720")
        f4 = "%s/%s" % (tempdir, "service-perfdata.1479712720")
        p1 = f1 + perfdata_dispatcher.IN_PROCESS_SUFFIX + "0"
        p2 = f2 + perfdata_dispatcher.IN_PROCESS_SUFFIX + "1"

        # Nagios put files
        self.touch(f1)
        self.touch(f2)

        # The queues must be fill
        p._run_job()
        self.assertEqual(2, queue.qsize())
        self.assertEqual(2, len(p._local_queue))

        # Processors takes files
        queue.get()
        queue.get()

        # The main queue have been emptied
        # and the local tracking is still OK
        p._run_job()
        self.assertEqual(0, queue.qsize())
        self.assertEqual(2, len(p._local_queue))

        # Processors process files
        os.rename(f1, p1)
        os.rename(f2, p2)

        # The main queue is still empty
        # and the local tracking should be gone
        p._run_job()
        self.assertEqual(0, queue.qsize())
        self.assertEqual(0, len(p._local_queue))

        # Nagios put new files
        self.touch(f3)
        self.touch(f4)

        # New stuffs should be there
        p._run_job()
        self.assertEqual(2, queue.qsize())
        self.assertEqual(2, len(p._local_queue))

        # Processors takes files
        queue.get()
        queue.get()

        # Processors finish to push them
        os.remove(p1)
        os.remove(p2)
        os.remove(f3)
        os.remove(f4)

        # We have nothing to do anymore
        p._run_job()
        self.assertEqual(0, queue.qsize())
        self.assertEqual(0, len(p._local_queue))
