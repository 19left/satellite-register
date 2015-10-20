__author__ = 'scott.a.clark'

import os
from platform import dist
import socket
import subprocess


class CurrentHost(object):
    def __init__(self, clo, sat):
        self.satellite = sat

        self.fqdn = socket.getfqdn()
        hparts = self.fqdn.split(".", 1)
        self.alias = hparts[0]
        self.domain = hparts[1]

        self.ipaddress = socket.gethostbyname(self.fqdn)

        # Process system-derivable information
        ps = subprocess.Popen("/sbin/ip r | grep default | awk '{print $3}'", shell=True, stdout=subprocess.PIPE)
        out = ps.communicate()
        if out and "." in out:
            self.gateway = out

        # Populate data from command line
        # We'll just tack the values on
        self.__dict__.update(clo.__dict__)

        # Placeholder value. We can't know this until we've actually registered
        self.uuid = None

        # Check for the existance of the RHEL product certificate and download it if absent
        if not os.listdir("/etc/pki/product") or not os.path.isfile("/etc/pki/product/69.pem"):
            # Get the appropriate certificate file by major version
            cert = "http://%s/pub/rhel%sproduct.pem" % (sat, dist()[1][0])
            subprocess.call(["wget", "-qO", "/etc/pki/product/69.pem", cert])
            if not os.path.exists("/etc/pki/product/69.pem"):
                raise CurrentHostException("Current Host does not have a valid product, Cannot register.")

    def __str__(self):
        for k, v in self.__dict__.iteritems():
            print "%s:               %s" % (k, v)

    def register(self):
        args = ["/usr/sbin/subscription-manager", "register", "--org", self.organization,
                "--activationkey", self.activationkey]
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
