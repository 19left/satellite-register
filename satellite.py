__author__ = 'scott.a.clark'

import os
import socket
import subprocess

from platform import dist
from yum import YumBase

# Conditional imports
try:
    # simplejson is only available in Python 2.5+ (hence no RHEL 5)
    import simplejson as json
    # requests
except ImportError:
    import json

class CurrentHost:
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
            subprocess.call(["wget", "-qO", "/etc/pki/product/69.pem", cert])
            if not os.path.exists("/etc/pki/product/69.pem"):
                raise CurrentHostException("Current Host does not have a valid product, Cannot register.")

    def __str__(self):
        __str = ""
        for k, v in self.__dict__.iteritems():
            __str += "%s:               %s\n" % (k, v)
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

        ps = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = ps.communicate()

        if not out or "--force" in err:
            args.append("--force")
            ps = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = ps.communicate()

        if out:
            # Capture system UUID from subscription-manager output
            list_out = out.split(': ')
            self.uuid = list_out[1]
        else:
            raise CurrentHostException("System did not register properly, even with --force option")


class CurrentHostException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "CurrentHostException: %s" % self.msg


class SatelliteYum(YumBase):
    def __init__(self):
        super(self.__class__, self).__init__()
        self.conf.assumeyes = True

    def process(self):
        self.resolveDeps()
        self.processTransaction()

    def find(self, pkgname):
        return self.rpmdb.searchNevra(name=pkgname)

    def update_rhsm(self):
        """
        update_rhsm: Determines if subscription-manager is installed and ensures latest.
        """
        if self.find("subscription-manager"):
            self.update(name="subscription-manager")
        else:
            self.install(name="subscription-manager")

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
        self.remove(name="yum-rhn-plugin")
        self.remove(name="rhncfg*")
        self.remove(name="rhn-client-tools")
        self.remove(name="rhnlib")
        self.remove(name="jabberpy")
        self.remove(name="osad")
        self.process()

    def localinstall_katelloca(self, src, tmpdir="/tmp"):
        """
        localinstall_katelloca: Install the Satellite 6 CA cert package
        """
        if not self.find("wget"):
            self.install(name="wget")
            self.process()

        rpm = "katello-ca-consumer-latest.noarch.rpm"
        spath = "http://%s/pub/%s" % (src, rpm)
        dpath = "%s/%s" % (tmpdir, rpm)
        subprocess.call(["/usr/bin/wget", "-qO", dpath, spath])

        self.conf.gpgcheck = False
        self.installLocal(dpath)
        self.process()
        self.conf.gpgcheck = True

    def manage_localrepo(self, repo, action=1):
        repolist = self.repos.findRepos(repo)
        for r in repolist:
            if action is 0:
                r.disablePersistent()
            else:
                r.enablePersistent()

    def clean_all(self):
        self.cleanPackages()
        self.cleanHeaders()
        self.cleanMetadata()
        self.cleanSqlite()

    def install_sat6(self):
        self.install(name="katello-agent")
        self.install(name="puppet")
        self.process()


class SatellitePuppet(object):
    def __init__(self, master):
        self.__file = "/etc/puppet/puppet.conf"
        self.master = master

        # Update the configuration file
        pconf = open(self.__file)
        contents = pconf.readlines()
        pconf.close()

        i = (contents.index('    classfile = $vardir/classes.txt\n')) + 1

        # You have to write these in reverse order for the insert to work
        contents.insert(i, "    server = %s\n" % self.master)
        contents.insert(i, "    ca_server = %s\n" % self.master)
        contents.insert(i, "    daemon = false\n")
        contents.insert(i, "    ignoreschedules = true\n")
        contents.insert(i, "    report = true\n")
        contents.insert(i, "    pluginsync = true\n")
        contents.insert(i, "    # Satellite 6 Environment Configuration\n")
        contents.insert(i, "\n")

        pconf = open(self.__file, 'w')
        pconf.writelines(contents)
        pconf.close()

    def run(self):
        ps = subprocess.Popen(['/usr/bin/puppet', 'agent', '-t'], stdout=subprocess.PIPE)
        return ps.communicate()

class SatellitePuppetException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "SatellitePuppetException: %s" % self.msg

class SatelliteAPI():
    def __init__(self):
        try:
            import requests
        except ImportError:
            # Possible causes:
            #   1) RPM is not installed
            #   2) RHEL 5 does not have this module
            if int(dist()[1][0]) is 5:
                raise SatelliteAPIException("Cannot use Satellite API on RHEL 5 systems.")
            else:
                # We're on 6 or 7--make sure the python-requests RPM is installed.
                # TODO: Install python-requests


class SatelliteAPIException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return "SatelliteAPIException: %s" % self.msg
