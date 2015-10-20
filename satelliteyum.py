__author__ = 'scott.a.clark'

import os
from yum import YumBase
from subprocess import call


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
        call(["/usr/bin/wget", "-qO", dpath, spath])

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
