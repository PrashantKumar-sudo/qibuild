## Copyright (c) 2012, 2013 Aldebaran Robotics. All rights reserved.
## Use of this source code is governed by a BSD-style license that can be
## found in the COPYING file.

"""Run git grep on every project

Options are the same as in git grep, e.g.:

  qisrc grep -- -niC2 foo

"""

import os
import sys

from qisys import ui
import qisys
import qisrc
import qisys.parsers
import qisrc.parsers
import qisrc.cmdparse

def configure_parser(parser):
    """Configure parser for this action."""
    qisrc.parsers.worktree_parser(parser)
    qisys.parsers.project_parser(parser, positional=False)
    parser.add_argument("--path", help="type of patch to print",
            default="project", choices=['none', 'absolute', 'worktree', 'project'])
    parser.add_argument("git_grep_opts", metavar="-- git grep options", nargs="*",
                        help="git grep options preceeded with -- to escape the leading '-'")
    parser.add_argument("pattern", metavar="PATTERN",
                        help="pattern to be matched")

def do(args):
    """Main entry point."""
    qiwt = qisys.worktree.open_worktree(args.worktree)
    git_grep_opts = args.git_grep_opts
    if args.path == 'none':
        git_grep_opts.append("-h")
    else:
        git_grep_opts.append("-H")
        if args.path == 'absolute' or args.path == 'worktree':
            git_grep_opts.append("-I")
            git_grep_opts.append("--null")
    git_grep_opts.append(args.pattern)

    retcode = 0
    projects = qisrc.cmdparse.projects_from_args(args, qiwt)
    projects = qisrc.git.get_git_projects(projects)
    for project in projects:
        ui.info(ui.green, "Looking in", project.src, "...")
        git = qisrc.git.Git(project.path)
        (status, out) = git.call("grep", *git_grep_opts, raises=False)
        if out != "":
            if args.path == 'absolute' or args.path == 'worktree':
                lines = out.splitlines()
                out_lines = list()
                for line in lines:
                    line_split = line.split('\0')
                    prepend = project.src if args.path == 'worktree' else project.path
                    line_split[0] = os.path.join(prepend, line_split[0])
                    out_lines.append(":".join(line_split))
                out = '\n'.join(out_lines)
            print out
        if status != 0:
            retcode = 1
    sys.exit(retcode)
