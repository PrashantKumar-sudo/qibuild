#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2012-2018 SoftBank Robotics. All rights reserved.
# Use of this source code is governed by a BSD-style license (see the COPYING file).
""" Toolchain """
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import os
import operator

from qisys import ui
import qisys.sh
import qisrc.git
import qitoolchain.database


class Toolchain(object):
    """ Toolchain Class """

    def __init__(self, name):
        """ Toolchain Init """
        self.name = name
        self.feed_url = None
        # Used when feed_url is a git URL
        self.feed_name = None
        self.feed_branch = None
        self.config_path = qisys.sh.get_config_path("qi", "toolchains", "%s.xml" % self.name)
        self.register()
        self.load()
        self.toolchain_file = qisys.sh.get_share_path(
            "qi",
            "toolchains",
            self.name,
            "toolchain-%s.cmake" % self.name
        )
        db_path = qisys.sh.get_share_path("qi", "toolchains", "%s.xml" % self.name)
        if not os.path.exists(db_path):
            with open(db_path, "w") as fp:
                fp.write("<toolchain />")
        self.db = qitoolchain.database.DataBase(name, db_path)
        self.generate_toolchain_file()

    @property
    def packages(self):
        """ Retrun the QiPackages Sorted by Name """
        return sorted(self.db.packages.values(), key=operator.attrgetter("name"))

    def load(self):
        """ Load the Toolchain """
        tree = qisys.qixml.read(self.config_path)
        root = tree.getroot()
        self.feed_url = root.get("feed")
        self.feed_name = root.get("name")
        self.feed_branch = root.get("branch")

    def save(self):
        """ Save the Toolchain """
        tree = qisys.qixml.read(self.config_path)
        root = tree.getroot()
        root.set("feed", self.feed_url)
        if self.feed_branch:
            root.set("branch", self.feed_branch)
        if self.feed_name:
            root.set("name", self.feed_name)
        qisys.qixml.write(root, self.config_path)

    def register(self):
        """ Register the Toolchain if it doesn't exists """
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w") as fp:
                fp.write("<toolchain />")

    def unregister(self):
        """ Unregister the Toolchain """
        qisys.sh.rm(self.config_path)

    def update(self, feed_url=None, branch=None, name=None):
        """ Update the Toolchain """
        if feed_url is None:
            feed_url = self.feed_url
        if name is None:
            name = self.feed_name
        if branch is None:
            branch = self.feed_branch
        self.db.update(feed_url, branch=branch, name=name)
        self.feed_url = feed_url
        self.feed_branch = branch
        self.feed_name = name
        self.save()
        self.generate_toolchain_file()

    def add_package(self, package):
        """ Add a Package to the Toolchain """
        self.db.add_package(package)
        self.db.save()
        self.generate_toolchain_file()

    def remove_package(self, name):
        """ Remove a Package from the Toolchain """
        self.db.remove_package(name)
        self.db.save()
        self.generate_toolchain_file()

    def solve_deps(self, packages, dep_types=None):
        """ Solve Dependencies """
        return self.db.solve_deps(packages, dep_types=dep_types)

    def get_package(self, name, raises=True):
        """ Get a Package """
        return self.db.get_package(name, raises=raises)

    def remove(self):
        """ Remove the Toolchain """
        self.db.remove()
        self.unregister()

    def generate_toolchain_file(self):
        """ Generate the Toolchain File """
        lines = [
            "# Autogenerated file. Do not edit\n",
            "# Make sure we don't keep adding elements to this list:\n",
            "set(CMAKE_PREFIX_PATH \"\" CACHE INTERNAL \"\" FORCE)\n",
            "set(CMAKE_FRAMEWORK_PATH \"\" CACHE INTERNAL \"\" FORCE)\n",
        ]
        for package in self.packages:
            if package.toolchain_file:
                tc_file = qisys.sh.to_posix_path(package.toolchain_file)
                lines.append('include("%s")\n' % tc_file)
        for package in self.packages:
            if not package.path:
                raise Exception(
                    " Incorrect database configuration in %s: no path for package %s" % (
                        self.db.db_path, package.name
                    )
                )
        oldlines = list()
        if os.path.exists(self.toolchain_file):
            with open(self.toolchain_file, "r") as fp:
                oldlines = fp.readlines()
        # Do not write the file if it's the same
        if lines != oldlines:
            with open(self.toolchain_file, "w") as fp:
                lines = fp.writelines(lines)

    def get_sysroot(self):
        """
        Get the sysroot of the toolchain.
        Assume that one and exactly one of the packages inside
        the toolchain has a 'sysroot' attribute.
        """
        for package in self.packages:
            if package.sysroot:
                return package.sysroot
        return None

    def get_cross_gdb(self):
        """
        Get the cross-gdb path from the toolchain.
        Assume that one and exactly one of the packages inside
        the toolchain has a 'cross_gdb' attribute.
        """
        for package in self.packages:
            if package.cross_gdb:
                return package.cross_gdb
        return None

    @property
    def cross(self):
        """ Return True if a Cross Toolchain (With SysRoot). """
        return self.get_sysroot() is not None

    def __eq__(self, other):
        """ Return True if the Toolchain has the same name """
        return self.name == other.name

    def __ne__(self, other):
        """ Return True if the Toolchain doesn't have the same name """
        return not self.__eq__(other)

    def __str__(self):
        """ String Representation of the Toochain """
        git_path = qisys.sh.get_share_path("qi", "toolchains", self.name + ".git")
        sha1 = None
        if os.path.exists(git_path):
            git = qisrc.git.Git(git_path)
            _, sha1 = git.call("rev-parse", "HEAD", raises=False)
        res = "Toolchain %s\n" % self.name
        if self.feed_url:
            res += "Using feed from %s" % self.feed_url
            if self.feed_name:
                res += " (feeds/%s.xml)" % self.feed_name
            if self.feed_branch:
                res += " on %s" % self.feed_branch
            if sha1:
                res += " - %s" % sha1[:8]
            res += "\n"
        else:
            res += "No feed\n"
        if self.packages:
            res += "  Packages:\n"
        else:
            res += "No packages\n"
        sorted_packages = sorted(self.packages)
        for package in sorted_packages:
            res += ui.indent(package.name, 2)
            if package.version:
                res += " " + package.version
            res += "\n"
            if package.path:
                res += ui.indent("in " + package.path, 3) + "\n"
        return res


def get_tc_names():
    """ Return the Names of the Toolchains """
    configs_path = qisys.sh.get_config_path("qi", "toolchains")
    if not os.path.exists(configs_path):
        return list()
    contents = os.listdir(configs_path)
    contents = sorted([x for x in contents if x.endswith(".xml")])
    return [x.replace(".xml", "") for x in contents]


def get_default_packages_path(tc_name):
    """ Return the Default Toolchains Path and Create it if needed """
    root = qisys.sh.get_share_path("qi", "toolchains")
    res = os.path.join(root, tc_name)
    qisys.sh.mkdir(res, recursive=True)
    return res
