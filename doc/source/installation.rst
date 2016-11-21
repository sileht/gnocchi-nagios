============
Installation
============

At the command line::

    $ pip install gnocchi-nagios

Or, if you have virtualenvwrapper installed::

    $ mkvirtualenv gnocchi-nagios
    $ pip install gnocchi-nagios


=============
Nagios/Icinga
=============

This is example of perdata configuration for Gnocchi-nagios

Preparing working directories::

    $ mkdir -p /var/spool/gnocchi-nagios/{nagios, ready}

In /etc/nagios3/nagios.conf::

.. code-block:: ini

    host_perfdata_file_mode=a
    host_perfdata_file_processing_interval=5
    host_perfdata_file_template=DATATYPE::HOSTPERFDATA\tTIMET::$TIMET$\tHOSTNAME::$HOSTNAME$\tHOSTPERFDATA::$HOSTPERFDATA$\t$\tHOSTSTATE::$HOSTSTATE$\tHOSTSTATETYPE::$HOSTSTATETYPE$

    service_perfdata_file_mode=a
    service_perfdata_file_processing_interval=5
    service_perfdata_file_template=DATATYPE::SERVICEPERFDATA\tTIMET::$TIMET$\tHOSTNAME::$HOSTNAME$\tSERVICEDESC::$SERVICEDESC$\tSERVICEPERFDATA::$SERVICEPERFDATA\tHOSTSTATE::$HOSTSTATE$\tHOSTSTATETYPE::$HOSTSTATETYPE$\tSERVICESTATE::$SERVICESTATE$\tSERVICESTATETYPE::$SERVICESTATETYPE$

    # NPCD bulk system
    host_perfdata_file=/var/spool/gnocchi-nagios/nagios/host-perfdata
    host_perfdata_file_processing_command=gnocchi-nagios-host

    service_perfdata_file=/var/spool/gnocchi-nagios/nagios/service-perfdata
    service_perfdata_file_processing_command=gnocchi-nagios-service


In /etc/nagios3/conf.d/gnocchi-nagios.cfg:

.. code-block::

    define command {
            command_name    gnocchi-nagios-service
            command_line    /bin/mv /var/spool/gnocchi-nagios/nagios/service-perfdata /var/spool/gnocchi-nagios/ready/service-perfdata.$TIMET$
    }

    define command {
            command_name    gnocchi-nagios-host
            command_line    /bin/mv /var/spool/gnocchi-nagios/nagios/host-perfdata /var/spool/gnocchi-nagios/ready/host-perfdata.$TIMET$
    }


=======
Gnocchi
=======

Installation and configuration of Gnocchi can be found `here <http://gnocchi.xyz/>`_

Once it's setupped, you can configure gnocchi-nagios like this:

.. code-block:: ini

   [DEFAULT]
   spool_directory = /var/spool/gnocchi-nagios/ready

   [gnocchi]
   auth_type=gnocchi-noauth
   gnocchi_user_id = <uuid>
   gnocchi_project_id = <uuid>
   gnocchi_endpoint = <gnocchi_endpoint>
