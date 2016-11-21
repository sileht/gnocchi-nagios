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
import subprocess
import time

import fixtures

from gnocchi_nagios import cli
from gnocchi_nagios import gnocchi_client
from gnocchi_nagios import perfdata_dispatcher
from gnocchi_nagios.tests import base


class TestFunctional(base.TestCase):
    def setUp(self):
        super(TestFunctional, self).setUp()
        self.tempdir = self.useFixture(fixtures.TempDir()).path
        conf_content = """
[DEFAULT]
spool_directory = "%s"

[gnocchi]
auth_type = gnocchi-noauth
user_id = "nagios"
project_id = "nagios"
roles = admin
endpoint = "%s"
""" % (self.tempdir, os.getenv('PIFPAF_GNOCCHI_HTTP_URL'))

        self.conffile = self.create_tempfiles([('gnocchi-data.conf',
                                                conf_content)])[0]
        self.conf = cli.prepare_service([], [self.conffile])

    @staticmethod
    def touch(fname):
        with open(fname, 'a'):
            os.utime(fname, None)

    def test_main(self):
        self.subp = subprocess.Popen(['gnocchi-nagios',
                                      '--config-file=%s' % self.conffile],
                                     preexec_fn=os.setsid,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)

        time.sleep(2)
        if self.subp.poll() is not None:
            self.assertEqual(None, self.subp.stdout.read())
        self.addCleanup(self.subp.terminate)

        c = gnocchi_client.get_gnocchiclient(self.conf)
        rt = c.resource_type.get("nagios-service")
        expected_rt = {
            'attributes': {'host': {'max_length': 255,
                                    'min_length': 0,
                                    'required': True,
                                    'type': 'string'},
                           'name': {'max_length': 255,
                                    'min_length': 0,
                                    'required': True,
                                    'type': 'string'}},
            'name': 'nagios-service',
            'state': 'active'}
        self.assertEqual(expected_rt, rt)

    def test_dispatcher(self):
        queue = multiprocessing.Manager().Queue()
        p = perfdata_dispatcher.PerfdataDispatcher(0, self.conf, queue)

        f1 = "%s/%s" % (self.tempdir, "host-perfdata.1479712710")
        f2 = "%s/%s" % (self.tempdir, "service-perfdata.1479712710")
        f3 = "%s/%s" % (self.tempdir, "host-perfdata.1479712720")
        f4 = "%s/%s" % (self.tempdir, "service-perfdata.1479712720")
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
