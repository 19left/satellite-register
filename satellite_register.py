__author__ = 'scott.a.clark'

import satellite
import subprocess
from sys import exit


def do_satellite_register():
    u = ("Usage: %prog [options] capsule_fqdn\n"
         "capsule_fqdn is the fully-qualified domain of the Satellite Capsule endpoint to which you are registering.\n"
         "It may be the embedded Capsule within the Satellite master or any standalone Capsule in your environment.")

    parser = satellite.SatelliteOptParse(u)
    (clo, cla) = parser.parse_args()

    try:
        sy = satellite.SatelliteYum()
        me = satellite.CurrentHost(clo, cla[0])
        # Check the input with the user before proceeding if they have not used the -y option
        if not clo.yes:
            satellite.print_confirmation(me)

        # Proceed with script, noting short-circuits
        if not clo.skip_update_rhsm:
            print "Installing/Updating subscription-manager..."
            sy.get_latest("subscription-manager")
            sy.process()

        if not clo.skip_rhn_clean:
            print "Removing RHN Classic components..."
            sy.clean_rhn_classic()
            sy.update_components()

        if not clo.skip_katelloca:
            print "Installing katello-ca-consumer-latest..."
            # sy.localinstall_katelloca(me.master)
            sy.localinstall(rpm="katello-ca-consumer-latest.noarch.rpm", remotedir="pub", srcdir=clo.tmpdir,
                            remotehost=me.master, ssl=clo.ssl)

        if not clo.skip_register:
            print "Registering system with subscription-manager..."
            me.register()
            sy.clean_all()

        if not clo.skip_install:
            print "Installing Satellite 6 components..."
            sy.install_sat6_components()
            subprocess.call("/usr/sbin/katello-package-upload")

        if not clo.skip_puppet:
            print "Configuring Puppet..."
            if satellite.configure_puppet(me.master):
                # Puppet configuration succeeded, continue...otherwise skip runs. We're not ready.
                # First run generates certificate
                satellite.puppet_run()
                # If not autosigned, maybe additional code required here?
                # Second run validates certificate
                satellite.puppet_run()

                if int(me.majorver) == 7:
                    subprocess.call(["/usr/bin/systemctl", "enable", "puppet"])
                    subprocess.call(["/usr/bin/systemctl", "start", "puppet"])
                else:
                    subprocess.call(["/sbin/chkconfig", "puppet", "on"])
                    subprocess.call(["/sbin/service", "puppet", "start"])
    except satellite.CurrentHostException, che:
        print che
        exit(69)  # 69.pem is the certificate file for RHEL
    except Exception, e:
        # Catch-all Exception Handling
        exception_type = e.__class__.__name__
        if exception_type == "SystemExit":
            exit()
        else:
            print ">>>EXCEPTION(" + exception_type + "): " + str(e)
            exit(-1)


# Make this "runnable"
if __name__ == "__main__":
    do_satellite_register()
