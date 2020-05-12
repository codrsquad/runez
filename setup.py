#!/usr/bin/env python

"""
url: https://github.com/zsimic
download_url: archive/v{version}.tar.gz
"""

from setuptools import setup


# import os, sys
# print("environ: %s" % dict(os.environ))
# print("__package__: '%s'" % __package__)
# print("__name__: %s" % __name__)
# print("__file__: %s" % __file__)
# print("sys.argv: %s" % sys.argv)
# print("sys.exe: %s" % sys.executable)
# sys.exit(0)

setup(
    name="runez",
    setup_requires="setupmeta",
    versioning="dev",
    author="Zoran Simic zoran@simicweb.com",
)
