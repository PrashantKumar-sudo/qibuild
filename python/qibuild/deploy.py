## Copyright (c) 2012, 2013 Aldebaran Robotics. All rights reserved.
## Use of this source code is governed by a BSD-style license that can be
## found in the COPYING file.

""" Tools to deploy files to remote targets"""

import re
import os

import qisys.command
import qibuild.deploy
from qibuild.dependencies_solver import DependenciesSolver

FILE_SETUP_GDB  = """\
# gdb script generated by qiBuild

set architecture i386
set verbose
set sysroot %(sysroot)s
set solib-search-path %(solib_search_path)s
"""

FILE_SETUP_TARGET_GDB  = """\
# gdb script generated by qiBuild

source %(source_file)s
target remote %(remote_gdb_address)s
"""

FILE_REMOTE_GDBSERVER_SH = """\
#!/bin/bash
# script generated by qiBuild
# run a gdbserver on the remote target

here=$(cd $(dirname $0) ; pwd)

if ! [ "$#" -eq "1" ] ; then
  echo "please specify the binary to run"
  exit 1
fi

echo ""
echo "To connect to this gdbserver launch the following command in another terminal:"
echo "  %(gdb)s -x \"${here}/setup_target.gdb\" \"${here}/${1}\""
echo ""

#echo ssh %(remote)s -- gdbserver %(gdb_listen)s "%(remote_dir)s/${1}"
ssh %(remote)s -- gdbserver %(gdb_listen)s "%(remote_dir)s/${1}"
"""

def parse_url(remote_url):
    """ Parse a remote url

    :return: a tuple: (remote, server, remote_dir)

    Examples:

    >>> parse_url('nao@10.0.253.181:deploy')
    ('nao@10.0.253.181', '10.0.253.181', 'deploy')
    >>> parse_url('10.0.253.181:deploy')
    ('10.0.253.181', '10.0.253.181', 'deploy')
    >>> parse_url('10.0.253.181:')
    ('10.0.253.181', '10.0.253.181', '')
    >>> parse_url('10.0.253.181')
    Traceback (most recent call last):
        ...
        raise Exception(mess)

    Note that the if the user plays with the "hostname" option in its
    .ssh/config, the "server" part might not be a valid hostname. In such a
    case, the deploy will work (thanks to ssh) but the remote debugging will
    not.

    """

    match = re.match(r"""
        (?P<remote>
         ((?P<username>[a-zA-Z0-9\._-]+)@)?
         (?P<server>[a-zA-Z0-9\._-]+))
        :
        (?P<remote_dir>[a-zA-Z0-9\.~_/-]*)$
        """, remote_url, re.VERBOSE)
    # note: this regexp does not support having weird chars (such as @ or ?)
    # or spaces in remote_dir. At least it will complain.
    if not match:
        mess  = "Invalid remote url: %s\n" % remote_url
        mess += "Remote url should look like user@host:path or host:path"
        raise Exception(mess)
    groupdict = match.groupdict()
    return (groupdict["remote"], groupdict["server"], groupdict["remote_dir"])


def deploy(local_directory, remote_url, port=22, use_rsync=True):
    """Deploy a local directory to a remote url."""
    if use_rsync:
        # This is required for rsync to do the right thing,
        # otherwise the basename of local_directory gets
        # created
        local_directory = local_directory + "/."
        cmd = ["rsync",
            "--recursive",
            "--links",
            "--perms",
            "--times",
            "--specials",
            "--progress", # print a progress bar
            "--checksum", # verify checksum instead of size and date
            "--exclude=.debug/",
            "-e", "ssh -p %d" % port, # custom ssh port
            local_directory, remote_url
        ]
    else:
        # Default to scp
        cmd = ["scp", "-P", str(port), "-r", local_directory, remote_url]
    qisys.command.call(cmd)


def _generate_setup_gdb(dest, sysroot="\"\"", solib_search_path=[], remote_gdb_address=""):
    """ generate a script that connect a local gdb to a gdbserver """
    source_file = os.path.abspath(os.path.join(dest, "setup.gdb"))
    with open(source_file, "w+") as f:
        f.write(FILE_SETUP_GDB % { 'sysroot'            : sysroot,
                                   'solib_search_path'  : ":".join(solib_search_path)
                                 })
    with open(os.path.join(dest, "setup_target.gdb"), "w+") as f:
        f.write(FILE_SETUP_TARGET_GDB % { 'source_file'        : source_file,
                                          'remote_gdb_address' : remote_gdb_address
                                        })


def _generate_run_gdbserver_binary(dest, remote, gdb, gdb_listen, remote_dir):
    """ generate a script that run a program on the robot in gdbserver """
    if remote_dir == "":
        remote_dir = "."
    remote_gdb_script_path = os.path.join(dest, "remote_gdbserver.sh")
    with open(remote_gdb_script_path, "w+") as f:
        f.write(FILE_REMOTE_GDBSERVER_SH % { 'remote' : remote,
                                             'gdb_listen' : gdb_listen,
                                             'remote_dir' : remote_dir,
                                             'gdb' : gdb })
    os.chmod(remote_gdb_script_path, 0755)
    return remote_gdb_script_path

def _uniq(seq):
    """ Make sure no two same elements end up in the
    given sequence, using the idfun passed as parameter

    Note that the order is preserved

    """
    seen = set()
    result = []
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result

def _get_subfolder(directory):
    res = list()
    for root, dirs, files in os.walk(directory):
        new_root = os.path.abspath(root)
        if not os.path.basename(new_root).startswith(".debug"):
            res.append(new_root)
    return res


def _generate_solib_search_path(toc, project_name):
    """ generate the solib_search_path useful for gdb """
    res = []
    dep_solver = DependenciesSolver(projects=toc.projects,
                                    packages=toc.packages,
                                    active_projects=toc.active_projects)

    (r_project_names, _package_names, not_found) = dep_solver.solve([project_name])
    for p in r_project_names:
        ppath = toc.get_project(p).build_directory
        ppath = os.path.join(ppath, "deploy", "lib")
        res.extend(_get_subfolder(ppath))
    for p in _package_names:
        ppath = toc.toolchain.get(p)
        ppath = os.path.join(ppath, "lib")
        res.extend(_get_subfolder(ppath))
    return _uniq(res)

def generate_debug_scripts(toc, project_name, url, deploy_dir=None):
    """ generate all scripts needed for debug """
    (remote, server, remote_directory) = qibuild.deploy.parse_url(url)

    destdir = toc.get_project(project_name).build_directory
    if deploy_dir:
        destdir = deploy_dir

    solib_search_path = _generate_solib_search_path(toc, project_name)
    sysroot = None
    gdb = None
    message = None
    if toc.toolchain:
        sysroot = toc.toolchain.get_sysroot()
    if sysroot:
        # assume cross-toolchain
        gdb = toc.toolchain.get_cross_gdb()
        if gdb:
            message = "Cross-build. Using the cross-debugger provided by the toolchain."
        else:
            message = "Remote debugging not available: No cross-debugger found in the cross-toolchain"
    else:
        # assume native toolchain
        sysroot = "\"\""
        gdb = qisys.command.find_program("gdb")
        if gdb:
            message = "Native build. Using the debugger provided by the system."
        else:
            message = "Debugging not available: No debugger found in the system."
    if not gdb:
        return (None, message)
    if toc.toolchain:
        sysroot=toc.toolchain.get_sysroot()
    _generate_setup_gdb(destdir, sysroot=sysroot,
                        solib_search_path=solib_search_path,
                        remote_gdb_address="%s:2159" % server)
    gdb_script = _generate_run_gdbserver_binary(destdir, gdb=gdb, gdb_listen=":2159",
                                                remote=remote,
                                                remote_dir=remote_directory)
    return (gdb_script, message)
