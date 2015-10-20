__author__ = 'scott.a.clark'

import logging
from optparse import OptionParser
from currenthost import CurrentHost, CurrentHostException
from satelliteyum import SatelliteYum
from subprocess import call


def util_capture_options():
    """
    capture_options: Uses OptionParser to capture and return command line input
    :rtype: tuple -> option values captured
    """
    logging.debug("captureCommandLine")
    # parser.add_option("-a", "--application", dest="application",
    #                   help="three-letter customer code (optional)")
    parser.add_option("--activationkey", dest="activationkey",
                      help="Satellite Organization in which to register Current Host")
    parser.add_option("--capsule", dest="mycapsule",
                      help="Satellite Capsule that serves Current Host [Default: Main Satellite]")
    parser.add_option("--environment", dest="environment",
                      help="Lifecycle Environment in which to place Current Host")
    parser.add_option("--location", dest="location",
                      help="Location of Host")
    parser.add_option("--org", dest="organization",
                      help="Satellite Organization in which to register Current Host")
    parser.add_option("-y", "--yes", action="store_true", dest="yes",
                      help="Run script without any user interaction")
    parser.add_option("-h", "-?", "--help", action="store_true", dest="help",
                      help="Print usage statement")

    return parser.parse_args()


def print_confirmation():
    print("satellite_register will run on %s with the following information:" % me.fqdn)
    print me
    proceed = raw_input("Is this OK? [Y/n]")

    if proceed.upper() == "N" or proceed.upper() == "NO":
        print("Registration cancelled. Please check your input and try again.")
        exit(0)


parser = OptionParser()
(clo, cla) = util_capture_options()
try:
    me = CurrentHost(clo, cla[0])
except CurrentHostException, che:
    print che
    exit(69)  # 69.pem is the certificate file for RHEL

# Check the input with the user before proceeding
if clo.yes:
    print_confirmation()

sy = SatelliteYum()
sy.update_rhsm()
# TODO: manage NTP service
sy.clean_rhn_classic()
sy.install_sat6()
try:
    me.register()
except CurrentHostException, che:
    print che
    exit(1)

call("/usr/sbin/katello-package-upload")
