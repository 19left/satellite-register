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
    parser.add_option("--skip-install", action="store_true")
    parser.add_option("--skip-rhn-clean", action="store_true")
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
# Check the input with the user before proceeding if they have not used the -y option
if not clo.yes:
    print_confirmation()

try:
    me = satellite.CurrentHost(clo, cla[0])
    if not clo.skip_install:
        sy = satellite.SatelliteYum()
        sy.update_rhsm()
        if not clo.skip_rhn_clean:
            sy.clean_rhn_classic()
        sy.localinstall_katelloca(me.master)
        me.register()
        sy.install_sat6()

        call("/usr/sbin/katello-package-upload")

        puppet = satellite.SatellitePuppet(me.master)
        # First run generates certificate
        print puppet.run()
        # If not autosigned, maybe additional code required here?
        # Second run validates certificate
        print puppet.run()
except satellite.CurrentHostException, che:
    print che
    exit(69)  # 69.pem is the certificate file for RHEL
except Exception, e:
    # Catch-all Exception Handling
    exception_type = e.__class__.__name__
    if exception_type == "SystemExit":
        exit()
    else:
        print " EXCEPTION(" + exception_type + "): " + str(e)
        exit(-1)
