===============================
Gnocchi-nagios
===============================

.. image:: https://img.shields.io/pypi/v/gnocchi-nagios.svg
   :target: https://pypi.python.org/pypi/gnocchi-nagios/
   :alt: Latest Version

.. image:: https://img.shields.io/pypi/dm/gnocchi-nagios.svg
   :target: https://pypi.python.org/pypi/gnocchi-nagios/
   :alt: Downloads

.. image:: https://travis-ci.org/sileht/gnocchi-nagios.png?branch=master
   :target: https://travis-ci.org/sileht/gnocchi-nagios

Gnocchi-nagios allows to push Nagios perfdata to Gnocchi

* Free software: Apache license
* Documentation: http://gnocchi-nagios.readthedocs.org/
* Source: https://github.com/sileht/gnocchi-nagios
* Bugs: https://github.com/sileht/gnocchi-nagios/issues
* Contribution via Github pull requests: https://github.com/sileht/gnocchi-nagios/pulls

============
Installation
============

At the command line::

    $ pip install gnocchi-nagios

Or, if you have virtualenvwrapper installed::

    $ mkvirtualenv gnocchi-nagios
    $ pip install gnocchi-nagios


===========================
Nagios/Icinga configuration
===========================

This is example of perfdata configuration for Gnocchi-nagios

Preparing working directories::

    $ mkdir -p /var/spool/gnocchi-nagios/{nagios, ready}

In /etc/nagios3/nagios.conf:

.. code-block:: ini

    host_perfdata_file_mode=a
    host_perfdata_file_processing_interval=5
    host_perfdata_file_template=DATATYPE::HOSTPERFDATA\tTIMET::$TIMET$\tHOSTNAME::$HOSTNAME$\tHOSTPERFDATA::$HOSTPERFDATA$\t$\tHOSTSTATE::$HOSTSTATE$\tHOSTSTATETYPE::$HOSTSTATETYPE$

    service_perfdata_file_mode=a
    service_perfdata_file_processing_interval=5
    service_perfdata_file_template=DATATYPE::SERVICEPERFDATA\tTIMET::$TIMET$\tHOSTNAME::$HOSTNAME$\tSERVICEDESC::$SERVICEDESC$\tSERVICEPERFDATA::$SERVICEPERFDATA\tHOSTSTATE::$HOSTSTATE$\tHOSTSTATETYPE::$HOSTSTATETYPE$\tSERVICESTATE::$SERVICESTATE$\tSERVICESTATETYPE::$SERVICESTATETYPE$

    host_perfdata_file=/var/spool/gnocchi-nagios/nagios/host-perfdata
    host_perfdata_file_processing_command=gnocchi-nagios-host

    service_perfdata_file=/var/spool/gnocchi-nagios/nagios/service-perfdata
    service_perfdata_file_processing_command=gnocchi-nagios-service


In /etc/nagios3/conf.d/gnocchi-nagios.cfg:

.. code-block:: ini

    define command {
            command_name    gnocchi-nagios-service
            command_line    /bin/mv /var/spool/gnocchi-nagios/nagios/service-perfdata /var/spool/gnocchi-nagios/ready/service-perfdata.$TIMET$
    }

    define command {
            command_name    gnocchi-nagios-host
            command_line    /bin/mv /var/spool/gnocchi-nagios/nagios/host-perfdata /var/spool/gnocchi-nagios/ready/host-perfdata.$TIMET$
    }


=============
Gnocchi Setup
=============

Installation and configuration of Gnocchi can be found `here <http://gnocchi.xyz/>`_


Don't forget to create archive policies and archive policies rules that match your needs.

==============
Gnocchi-nagios
==============

Once it's setup, you can configure gnocchi-nagios by creating a gnocchi-nagios.conf:

.. code-block:: ini

   [DEFAULT]
   spool_directory = /var/spool/gnocchi-nagios/ready

   [gnocchi]
   auth_type = gnocchi-noauth
   roles = admin
   user_id = nagios
   project_id = nagios
   endpoint = http://localhost:8041


Note: Gnocchi-data assumes nagios TIMET epoch are in UTC


And then run it with:

.. code-block:: shell

    $ gnocchi-nagios --config-file=gnocchi-nagios.conf

To get all configuration option you can run

.. code-block:: shell

    $ tox -egenconfig
    $ less etc/gnocchi-nagios/gnocchi-nagios.conf
