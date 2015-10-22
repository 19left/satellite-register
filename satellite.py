__author__ = 'scott.a.clark'


import os
from platform import dist
import socket
import subprocess
from yum import YumBase


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

    def localinstall_katelloca(self, sat, tmpdir):
        """
        localinstall_katelloca: Install the Satellite 6 CA cert package
        """
        if not self.find("wget"):
            self.install(name="wget")
            self.process()

        rpm = "katello-ca-consumer-latest.noarch.rpm"
        spath = "http://%s/pub/%s" % (sat, rpm)
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


class Service:
    def __init__(self, name, rpm=None):
        """
        *** THIS CLASS SHOULD BE OVERRIDDEN ***
        __init__
        :param name: name of service to manage
        :param rpm: name of rpm (if different from service name)
        """
        self.name = name
        if not rpm:
            self.rpm = rpm
        else:
            self.rpm = name

        self.enabled = False

        # Check if service is installed, enabled
        self.yum = YumBase()
        if self.rpm:
            self.installed = self.yum.rpmdb.searchNevra(name=self.rpm)
        else:
            self.installed = self.yum.rpmdb.searchNevra(name=self.name)

        # To check if we're actually enabled, we'll need to override with version-specific
        # commands: RHEL 5/6 will use service/chkconfig; RHEL 7 uses systemctl

    def install(self):
        if not self.installed:
            self.yum.install(name=self.rpm)
            self.yum.resolveDeps()
            self.yum.processTransaction()

    def remove(self):
        if self.installed:
            self.yum.remove(name=self.rpm)
            self.yum.resolveDeps()
            self.yum.processTransaction()

class SysVService(Service):
    def __init__(self, name, rpm):
        super(self.__class__, self).__init__(name, rpm)
        self.check_command = "/sbin/chkconfig"
        self.manage_command = "/sbin/service"
        if self.installed:
            # Use SysV command to check if enabled
            self.enabled = not subprocess.call([self.check_command, self.name])

    def enable(self):
        if self.installed and not self.enabled:
            subprocess.call([self.check_command, self.name, "on"])

    def disable(self):
        if self.installed and self.enabled:
            subprocess.call([self.check_command, self.name, "off"])

    def start(self):
        if self.