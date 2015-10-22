__author__ = 'scott.a.clark'

import logging
from optparse import OptionParser
import satellite
from subprocess import call


def util_capture_options():
    """
    capture_options: Uses OptionParser to capture and return command line input
    :rtype: tuple -> option values captured
    """
    logging.debug("captureCommandLine")
    # parser.add_option("-a", "--application", dest="application",
    #                   help="three-letter customer code (optional)")
    parser.add_option("-a", "--activationkey", metavar="KEY",
                      help="Register to Capsule using activation key KEY")
    parser.add_option("-e", "--environment", metavar="LCE",
                      help="Lifecycle Environment in which to place Current Host (Activation Key overrides this)")
    parser.add_option("-l", "--location", metavar="LOC",
                      help="Location of Host")
    parser.add_option("-o", "--organization", metavar="ORG",
                      help="Satellite Organization in which to register Current Host [REQUIRED]")
    parser.add_option("-c", "--hostcollection", action="append", metavar="HC",
                      help="Additional host collections to associate (may be specified more than once)")
    parser.add_option("--skip-install", action="store_true", )
    parser.add_option("-y", "--yes", action="store_true", help="Run script without any user interaction")

    return parser.parse_args()


def print_confirmation():
    print("satellite_register will run on %s with the following information:" % me.fqdn)
    print me

    go = False
    while go is False:
        proceed = raw_input("Is this OK? [Y/n]").upper()
        if proceed is "N" or proceed is "NO":
            print("Registration cancelled. Please check your input and try again.")
            exit(0)
        elif proceed is "Y" or proceed is "YES":
            go = True
        else:
            print("Invalid input: Please answer Y/yes or N/no.")


usage = ("Usage: %prog [options] capsule_fqdn\n"
         "capsule_fqdn is the fully-qualified domain of the Satellite Capsule endpoint to which you are registering.\n"
         "It may be the embedded Capsule within the Satellite master or any standalone Capsule in your environment.")

parser = OptionParser(usage)
(clo, cla) = util_capture_options()
# Check the input with the user before proceeding
if clo.yes:
    print_confirmation()

if not clo.skip_install:
    sy = satellite.SatelliteYum()
    sy.update_rhsm()
    # TODO: manage NTP service
    sy.clean_rhn_classic()
    sy.install_sat6()

try:
    me = satellite.CurrentHost(clo, cla[0])
    me.register()
except satellite.CurrentHostException, che:
    print che
    exit(69)  # 69.pem is the certificate file for RHEL


call("/usr/sbin/katello-package-upload")
