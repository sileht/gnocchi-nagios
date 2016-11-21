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

import multiprocessing

import cotyledon
from cotyledon import oslo_config_glue
from keystoneauth1 import loading as ka_loading
from oslo_config import cfg
from oslo_log import log
import pbr

from gnocchi_nagios import gnocchi_client
from gnocchi_nagios import opts
from gnocchi_nagios import perfdata_dispatcher
from gnocchi_nagios import perfdata_processor

LOG = log.getLogger(__name__)


class GnocchiNagiosServiceManager(cotyledon.ServiceManager):
    def __init__(self, conf):
        super(GnocchiNagiosServiceManager, self).__init__()
        oslo_config_glue.setup(self, conf)

        self.conf = conf
        self.queue = multiprocessing.Manager().Queue()

        self.add(perfdata_dispatcher.PerfdataDispatcher,
                 args=(self.conf, self.queue))
        self.processor_id = self.add(
            perfdata_processor.PerfdataProcessor, args=(self.conf, self.queue),
            workers=conf.workers)

        self.register_hooks(on_reload=self.on_reload)

    def on_reload(self):
        # NOTE(sileht): We do not implement reload() in Workers so all workers
        # will received SIGHUP and exit gracefully, then their will be
        # restarted with the new number of workers. This is important because
        # we use the number of worker to declare the capability in tooz and
        # to select the block of metrics to proceed.
        self.reconfigure(self.processor_id,
                         workers=self.conf.workers)

    def run(self):
        super(GnocchiNagiosServiceManager, self).run()
        self.queue.close()


def get_default_workers():
    try:
        default_workers = multiprocessing.cpu_count() or 1
    except NotImplementedError:
        default_workers = 1
    return default_workers


def prepare_service(args=None, default_config_files=None):
    conf = cfg.ConfigOpts()
    # opts.set_defaults()
    log.register_options(conf)

    # Register our own Gnocchi options
    for group, options in opts.list_opts():
        conf.register_opts(list(options),
                           group=None if group == "DEFAULT" else group)
    ka_loading.register_auth_conf_options(conf, 'gnocchi')
    ka_loading.register_session_conf_options(conf, 'gnocchi')

    conf.set_default("workers", get_default_workers())
    conf.set_default("auth_type", "gnocchi-noauth", "gnocchi")

    conf(args, project='gnocchi-nagios', validate_default_values=True,
         default_config_files=default_config_files,
         version=pbr.version.VersionInfo('gnocchi-nagios').version_string())

    log.set_defaults(default_log_levels=log.get_default_log_levels() +
                     ["passlib.utils.compat=INFO"])
    log.setup(conf, 'gnocchi-nagios')
    conf.log_opt_values(LOG, log.DEBUG)

    return conf


def main():
    conf = prepare_service()
    gnocchi_client.update_gnocchi_resource_type(conf)
    GnocchiNagiosServiceManager(conf).run()
