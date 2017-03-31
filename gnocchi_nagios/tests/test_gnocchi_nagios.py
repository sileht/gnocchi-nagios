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
from gnocchi_nagios import perfdata_processor
from gnocchi_nagios.tests import base


PERFDATA_SERVICE = """
DATATYPE::SERVICEPERFDATA\tTIMET::1479726660\tHOSTNAME::arn\tSERVICEDESC::Uptime\tSERVICEPERFDATA::uptime=9175101.06;;;;\tSERVICECHECKCOMMAND::check_mk-uptime\tHOSTSTATE::UP\tHOSTSTATETYPE::HARD\tSERVICESTATE::OK\tSERVICESTATETYPE::HARD
DATATYPE::SERVICEPERFDATA\tTIMET::1479726660\tHOSTNAME::arn\tSERVICEDESC::fs_/\tSERVICEPERFDATA::/=2169.12890625MB;3603.049099;4256.33705;0;4909.625 fs_size=4909.625MB;;;; growth=33.753218;;;; trend=-1.658471;;;0;204.567708 inodes_used=61167;294912;311296;0;327680\tSERVICECHECKCOMMAND::check_mk-df\tHOSTSTATE::UP\tHOSTSTATETYPE::HARD\tSERVICESTATE::OK\tSERVICESTATETYPE::HARD
"""  # noqa


class TestFunctional(base.TestCase):
    def setUp(self):
        super(TestFunctional, self).setUp()
        self.tempdir = self.useFixture(fixtures.TempDir()).path
        conf_content = """
[DEFAULT]
debug = False
spool_directory = "%s"

[gnocchi]
auth_type = gnocchi-basic
user = admin
roles = admin
endpoint = "%s"
""" % (self.tempdir, os.getenv('PIFPAF_GNOCCHI_HTTP_URL'))

        self.conffile = self.create_tempfiles([('gnocchi-data.conf',
                                                conf_content)])[0]
        self.conf = cli.prepare_service([], [self.conffile])

    @staticmethod
    def touch(fname, content=None):
        with open(fname, 'a') as f:
            if content is not None:
                f.write(content)
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
        f4 = "%s/%s" % (self.tempdir, "service-perfdata.1479712721")
        p1 = f1 + self.conf.file_picked_suffix + "0"
        p2 = f2 + self.conf.file_picked_suffix + "1"

        # Nagios put files
        self.touch(f1)
        self.touch(f2)

        # The queues must be fill
        p._run_job()
        self.assertEqual(1, queue.qsize())
        self.assertEqual(2, len(p._local_queue))

        # Processors takes files, ensure we have the both files returned
        paths = queue.get()
        self.assertEqual(2, len(paths))

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
        self.assertEqual(1, queue.qsize())
        self.assertEqual(2, len(p._local_queue))

        # Processors takes files, ensure we have the both files returned
        paths = queue.get()
        self.assertEqual(2, len(paths))

        # Processors finish to push them
        os.remove(p1)
        os.remove(p2)
        os.remove(f3)
        os.remove(f4)

        # We have nothing to do anymore
        p._run_job()
        self.assertEqual(0, queue.qsize())
        self.assertEqual(0, len(p._local_queue))

    def test_processor(self):
        gnocchi_client.update_gnocchi_resource_type(self.conf)

        f1 = "%s/%s" % (self.tempdir, "service-perfdata.1479712710")
        self.touch(f1, PERFDATA_SERVICE)

        p = perfdata_processor.PerfdataProcessor(0, self.conf, None)
        p._process_perfdata_files([f1])

        c = gnocchi_client.get_gnocchiclient(self.conf)
        resources = c.resource.list('nagios-service')
        self.assertEqual(1, len(resources))
        self.assertEqual('arn', resources[0]['original_resource_id'])
        self.assertEqual('arn', resources[0]['host'])

        metrics = c.metric.list()
        self.assertEqual(6, len(metrics))

        measures = c.metric.get_measures(
            "fs_@::trend",
            resource_id="arn",
            refresh=True)
        expected_measures = [
            ['2016-11-21T11:10:00+00:00', 300.0, -1.658471]
        ]
        self.assertEqual(expected_measures, measures)

        measures = c.metric.get_measures("Uptime::uptime", resource_id="arn",
                                         refresh=True)
        expected_measures = [
            [u'2016-11-21T11:10:00+00:00', 300.0, 9175101.06]]
        self.assertEqual(expected_measures, measures)
