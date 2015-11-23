import os
import socket
import subprocess

from platform import dist
from yum import YumBase, Errors
from optparse import OptionParser

# try:
#     import requests
# except ImportError:
#     # Possible causes:
#     #   1) RPM is not installed
#     #   2) RHEL 5 does not have this module
#     requests = None
#     if int(dist()[1][0]) == 5:
#         print("Cannot use Satellite API on RHEL 5 systems.")
#     else:
#         print("Cannot import requests module. Satellite API not available.")

# Conditional imports
try:
    # simplejson is only available in Python 2.5+ (hence no RHEL 5)
    import simplejson as json
    # requests
except ImportError:
    import json

__author__ = 'scott.a.clark'


class CurrentHost(object):
    def __init__(self, clo, cap):
        self.master = cap

        self.fqdn = socket.getfqdn()
        hparts = self.fqdn.split(".", 1)
        self.alias = hparts[0]
        self.domain = hparts[1]

        self.ipaddress = socket.gethostbyname(self.fqdn)

        self.majorver = dist()[1][0]

        # Process system-derivable information
        ps = subprocess.Popen("/sbin/ip r | grep default | awk '{print $3}'", shell=True, stdout=subprocess.PIPE)
        out = ps.communicate()
        if out and "." in out:
            self.gateway = out

        # Placeholder values. They will be updated either by clo below or reference
        self.organization = None
        self.activationkey = None
        self.environment = None
        self.hostcollection = None
        self.location = None
        self.uuid = None

        # Populate data from command line
        # We'll just tack the values on
        self.__dict__.update(clo.__dict__)

        # Check for the existance of the RHEL product certificate and download it if absent
        if not os.listdir("/etc/pki/product") or not os.path.isfile("/etc/pki/product/69.pem"):
            # Get the appropriate certificate file by major version
            cert = "http://%s/pub/rhel%sproduct.pem" % (self.master, self.majorver)
            subprocess.call(["/usr/bin/wget", "-qO", "/etc/pki/product/69.pem", cert])
            if not os.path.exists("/etc/pki/product/69.pem"):
                raise CurrentHostException("Current Host does not have a valid product, Cannot register.")

    def __str__(self):
        __str = ""
        for k, v in self.__dict__.iteritems():
            # Ignore run flags copied in from command-line options
            if "skip" in k or k == "yes":
                continue
            k += ":"
            __str += "%s%s\n" % (k.ljust(25), v)
        return __str

    def register(self):
        args = ["/usr/sbin/subscription-manager", "register"]
        if self.organization:
            args.extend(["--org", self.organization])
        else:
            raise CurrentHostException("Organization is required for registration")

        if self.activationkey:
            args.extend(["--activationkey", self.activationkey])
        else:
            args.extend(["--environment", self.environment])

        ps = subprocess.Popen(args, stdout=subprocess.PIPE)
        (out, err) = ps.communicate()
        if "--force" in out:
            print out
            go = False
            while go is False:
                proceed = raw_input("Force registration? [Y/n]: ").upper()
                if proceed == "N" or proceed == "NO":
                    print "Forced Registration cancelled."
                    return
                elif proceed == "Y" or proceed == "YES":
                    go = True
                else:
                    print("Invalid input: Please answer Y/yes or N/no.")

            args.append("--force")
            ps = subprocess.Popen(args, stdout=subprocess.PIPE)
            (out, err) = ps.communicate()
            if not out:
                raise CurrentHostException("System did not register properly, even with --force option")
            else:
                # Capture system UUID from subscription-manager output
                list_out = out.split(': ')
                self.uuid = list_out[1]
        elif not out:
            raise CurrentHostException("System failed to register. Check /var/log/rhsm/rhsm.log for more information.")
        else:
            # Capture system UUID from subscription-manager output
            list_out = out.split(': ')
            self.uuid = list_out[1]

            subprocess.call(["/usr/bin/yum", "clean", "all"])
            subprocess.call(["/usr/bin/yum", "makecache"])


class CurrentHostException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "CurrentHostException: %s" % self.msg


class SatelliteYum(YumBase):
    def __init__(self):
        YumBase.__init__(self)
        self.conf.assumeyes = True

        # We're only going to do this when API is ready to rock. Ignore for now.
        # try:
        #     self.get_latest("python-requests")
        # except Errors.InstallError:
        #     print "python-requests is not available for this system"

    def process(self):
        self.resolveDeps()
        self.processTransaction()
        for pkg in self.tsInfo.getMembers():
            print pkg.po.pkgtup
            self.tsInfo.remove(pkg.po.pkgtup)

    def find(self, pkgname):
        return self.rpmdb.searchNevra(name=pkgname)

    def get_latest(self, pkg):
        if self.find(pkg):
            self.update(name=pkg)
        else:
            self.install(name=pkg)

        self.process()

    def update_components(self):
        pkgs = ["yum-metadata-parser", "yum"]
        for i in pkgs:
            self.update(name=i)

        self.process()

    def clean_rhn_classic(self):
        """
        clean_rhn_classic: Remove packages specific to RHN Classic/Satellite 5 registration.
        """
        # Remove systemid to clean up client end
        sysidfile = "/etc/sysconfig/rhn/systemid"
        if os.path.isfile(sysidfile):
            os.remove(sysidfile)

        # Cleanup all RHN Classic/Sat5-related packages
        pkgs = ["yum-rhn-plugin", "rhncfg*", "rhn-client-tools", "rhnlib", "jabberpy", "osad"]
        gotone = False
        for i in pkgs:
            if self.find(i):
                self.remove(name=i)
                gotone = True

        if gotone:
            self.process()
        else:
            print "clean_rhn_classic: No RHN Classic components installed. Congratulations."

    def localinstall(self, rpm, srcdir="/tmp", remotehost=None, remotedir=None, ssl=True):
        dpath = "%s/%s" % (srcdir, rpm)
        spath = None
        if remotehost:
            if ssl:
                spath = "https://"
            else:
                spath = "http://"

            spath += "%s/" % remotehost
            if remotedir:
                spath += "%s/" % remotedir
            spath += rpm

            args = ["/usr/bin/wget", "-qO", dpath, spath]
            print args
            subprocess.call(args)

        if os.path.exists(dpath):
            self.conf.gpgcheck = False
            self.installLocal(dpath)
            self.process()
            self.conf.gpgcheck = True
        else:
            if remotehost:
                raise SatelliteYumException("Could not retrieve %s from %s. Check parameters" % (rpm, spath))
            else:
                raise SatelliteYumException("Could not find file %s for installation. Check paths." % dpath)

    def install_sat6_components(self):
        try:
            self.get_latest("katello-agent")
            self.get_latest("puppet")
        except Errors.InstallError, ie:
            print ie.__str__()
            raise SatelliteYumException("Satellite repositories did not configure properly. Please check components.")

    def manage_localrepo(self, repo, action=1):
        repolist = self.repos.findRepos(repo)
        for r in repolist:
            if action == 0:
                r.disablePersistent()
            else:
                r.enablePersistent()


class SatelliteYumException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "SatelliteYumException: %s" % self.msg


class SatelliteOptParse(OptionParser):
    def __init__(self, usage):
        OptionParser.__init__(self, usage)
        self.add_option("-a", "--activationkey", metavar="KEY",
                        help="Register to Capsule using activation key KEY")
        self.add_option("-e", "--environment", metavar="LCE",
                        help="Lifecycle Environment in which to place Current Host (Activation Key overrides this)")
        self.add_option("-l", "--location", metavar="LOC",
                        help="Location of Host")
        self.add_option("-o", "--organization", metavar="ORG",
                        help="Satellite Organization in which to register Current Host [REQUIRED]")
        self.add_option("-c", "--hostcollection", action="append", metavar="HC",
                        help="Additional host collections to associate (may be specified more than once)")
        self.add_option("--skip-update-rhsm", action="store_true",
                        help="Skips update of subscription-manager package")
        self.add_option("--skip-rhn-clean", action="store_true",
                        help="Skips removal of RHN Classic components")
        self.add_option("--skip-katelloca", action="store_true",
                        help="Skips install of Satellite/Capsule CA cert package")
        self.add_option("--skip-register", action="store_true",
                        help="Skips subscription-manager register step")
        self.add_option("--skip-install", action="store_true",
                        help="Preps system but does not install packages or register.")
        self.add_option("--skip-puppet", action="store_true",
                        help="Skips Puppet configuration (Content Host-only Registration)")
        self.add_option("--tmpdir", metavar="TMP", default="/tmp",
                        help="Directory for temporary files [Default: /tmp]")
        self.add_option("--disable-ssl", action="store_false", dest="ssl", default=True,
                        help="Disable SSL communication with Satellite/Capsule (not recommended)")
        self.add_option("-y", "--yes", action="store_true", help="Run script without any user interaction")


# class SatelliteAPI(object):
#     def __init__(self):
#         if not requests:
#             pass
#
#
# class SatelliteAPIException(Exception):
#     def __init__(self, msg):
#         self.msg = msg
#
#     def __str__(self):
#         return "SatelliteAPIException: %s" % self.msg

def print_confirmation(host):
    print("satellite_register will run on %s with the following information:" % host.fqdn)
    print host

    go = False
    while go is False:
        proceed = raw_input("Is this OK? [Y/n]: ").upper()
        if proceed == "N" or proceed == "NO":
            print("Registration cancelled. Please check your input and try again.")
            exit(0)
        elif proceed == "Y" or proceed == "YES":
            go = True
        else:
            print("Invalid input: Please answer Y/yes or N/no.")


def configure_puppet(master):
    # Update the configuration file
    __file = "/etc/puppet/puppet.conf"
    pconf = open(__file)
    contents = pconf.readlines()
    pconf.close()
    if not file_find(contents, "ca_server"):
        exactmatch = file_find(contents, "classfile")
        if exactmatch:
            i = (contents.index(exactmatch)) + 1
        else:
            print ("Puppet configuration does not match expected format. "
                   "Please review %s and configure manually." % __file)
            return False

        # You have to write these in reverse order for the insert to work
        contents.insert(i, "    server = %s\n" % master)
        contents.insert(i, "    ca_server = %s\n" % master)
        contents.insert(i, "    daemon = false\n")
        contents.insert(i, "    ignoreschedules = true\n")
        contents.insert(i, "    report = true\n")
        contents.insert(i, "    pluginsync = true\n")
        contents.insert(i, "    # Satellite 6 Environment Configuration\n")
        contents.insert(i, "\n")

        newpconf = open(__file, 'w')
        newpconf.writelines(contents)
        newpconf.close()
        return True
    else:
        print "Puppet has been configured before. Do this manually after script completes."
        return False


def puppet_run():
    subprocess.call(['/usr/bin/puppet', 'agent', '-t'], stdout=subprocess.PIPE)


def file_find(contents, search):
    for line in contents:
        if search in line:
            return line
    return None

