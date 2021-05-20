# zabbix-hpsa-status

Zabbix Template and python script with Low Level Discovery (LLD) for LSI MegaRAID controllers.

## Prerequisites:

    - MegaCLI64 [see installation instructions](https://gist.github.com/METAJIJI/cf859a7fc65a63690ecb208d11ea8407#file-install-megacli-md)
    - python 3.6
    - Zabbix 5

## Installation:

    - Add checkraid.py to the cron (* * * * * python3 /path/to/zabbix-lsi-status/checkraid.py  # require root privileges).
    - Import template lsi_status_template_zabbix5.xml to the Zabbix.
    - Add Template LSI MegaRAID Status to appropriate server.
    - Change selinux context for the LLD_JSON_PATH and LLD METRICS_PATH directories or disable it at all.

### Supported Controllers (depends on MegaCLI64)

## Tested on:

    - LSI Logic / Symbios Logic MegaRAID SAS 2108 [Liberator] (rev 05)
    - MegaCLI SAS RAID Management Tool  Ver 8.07.14
    - CentOS Linux release 7.5.1804 (Core)
    - Python Python 3.6.8
    - Zabbix 5.0.7