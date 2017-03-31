#
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

from keystoneauth1 import loading
from oslo_config import cfg


def list_opts():
    return [
        ('DEFAULT', [
            cfg.StrOpt('spool_directory',
                       default='/var/spool/gnocchi-nagios/ready',
                       help='The directory where nagios/icinga writes its '
                       'perfdata file'),
            cfg.IntOpt('workers', min=1,
                       default=1,
                       help='Number of workers for Gnocchi metric daemons. '
                       'By default the available number of CPU is used.'),
            cfg.IntOpt('file_per_worker_pass',
                       default=100,
                       help='Number of file read by a worker run'),
            cfg.StrOpt('file_picked_suffix',
                       default="-processed-by-worker-",
                       help='Suffix used when file is currently handled by a '
                       'worker'),
            cfg.IntOpt('interval_delay',
                       default=15,
                       help='Number of seconds between the spool directory '
                       'scanning'),
            cfg.BoolOpt('resubmit_on_crash',
                        default=False,
                        help='If gnocchi-metricd crashes during a perfdata '
                        'file processing we can\'t really known if the '
                        'Gnocchi have received the data of not. This option '
                        'allows to resubmit the perfdata a second time.'),
            cfg.StrOpt('slash_replacement',
                       default='@',
                       help=('replace / with this in resource_id and metric '
                             'name')),
            cfg.StrOpt('metric_delim',
                       default='::',
                       help=("metric name are built as "
                             "service_name<delim>perfdata_name")),
        ]),
        ('gnocchi', [
            cfg.StrOpt('region-name',
                       help='Region name to use for OpenStack service '
                       'endpoints.'),
            cfg.StrOpt('interface',
                       default='public',
                       choices=('public', 'internal', 'admin', 'auth',
                                'publicURL', 'internalURL', 'adminURL'),
                       help='Type of endpoint in Identity service catalog to '
                       'use for communication with OpenStack services.'),
        ]),
    ]


def list_keystoneauth_opts():
    # NOTE(sileht): the configuration file contains only the options
    # for the gnocchi-noauth plugin. But other options are possible.
    return [('gnocchi',
             loading.get_auth_common_conf_options() +
             loading.get_auth_plugin_conf_options('gnocchi-basic')
             )]
