#!/bin/bash
gpsd /dev/ttyS0 -F /var/run/gpsd.sock
i2cget -y 1 0x68 0x75


