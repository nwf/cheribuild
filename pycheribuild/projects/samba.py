#
# Copyright (c) 2018 Alex Richardson
# All rights reserved.
#
# This software was developed by SRI International and the University of
# Cambridge Computer Laboratory under DARPA/AFRL contract FA8750-10-C-0237
# ("CTSRD"), as part of the DARPA CRASH research programme.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#

import os
import shutil
from pathlib import Path

from .project import CheriConfig, DefaultInstallDir, GitRepository, MakeCommandKind, Project
from ..utils import OSInfo, set_env

SMB_OUT_OF_SOURCE_BUILD_WORKS = False


# Install samba from source (e.g. on MacOS where the builtin smbd is not usable by QEMU
class BuildSamba(Project):
    native_install_dir = DefaultInstallDir.BOOTSTRAP_TOOLS
    # TODO: the out-of source build doesn't work with bundled krb5
    if SMB_OUT_OF_SOURCE_BUILD_WORKS:
        make_kind = MakeCommandKind.CustomMakeTool
    else:
        build_in_source_dir = True
    repository = GitRepository("https://github.com/samba-team/samba.git",
                               default_branch="v4-12-stable", force_branch=True)

    def __init__(self, config: CheriConfig):
        super().__init__(config)
        self.configureCommand = self.source_dir / "configure"
        if SMB_OUT_OF_SOURCE_BUILD_WORKS:
            self.configureCommand = self.source_dir / "buildtools/bin/waf"
            self.configureArgs.insert(0, "configure")
            self.make_args.set_command(self.source_dir / "buildtools/bin/waf")
            self.make_args.add_flags("--blddir=" + str(self.build_dir))
            self.make_args.add_flags("--srcdir=" + str(self.source_dir))
            self.configureArgs.append("--blddir=" + str(self.build_dir))
            self.configureArgs.append("--srcdir=" + str(self.source_dir))
        # Based on https://willhaley.com/blog/compile-samba-macos/
        # Also try to disable everything that is not needed for QEMU user shares
        self.configureArgs.extend([
            "--disable-cephfs",
            "--disable-cups",
            "--disable-iprint",
            "--disable-glusterfs",
            "--disable-python",
            "--without-acl-support",
            "--without-ad-dc",
            "--without-ads",
            "--without-dnsupdate",
            "--without-ldap",
            "--without-ntvfs-fileserver",
            "--without-pam",
            "--without-quotas",
            "--without-regedit",
            "--without-syslog",
            "--without-utmp",
            "--without-winbind",
            # "--without-json-audit", "--without-ldb-lmdb", (only needed in master not 4.8 stable)
            "--without-libarchive",
            # Avoid depending on libraries from the build tree:
            "--bundled-libraries=talloc,tdb,pytdb,ldb,pyldb,tevent,pytevent",
            "--with-static-modules=ALL",
            "--prefix=" + str(self.install_dir),
            ])
        # Force python2 for now (since py3 seems broken)
        self.configureEnvironment["PYTHON"] = shutil.which("python")
        #  version 4.9 "--without-json-audit",
        self.configureArgs.append("--without-json")
        if OSInfo.IS_MAC:
            self.add_required_system_tool("/usr/local/opt/krb5/bin/kinit", homebrew="krb5")
            # TODO: brew --prefix krb5
            self.configureArgs.extend(["--with-system-mitkrb5", "/usr/local/opt/krb5"])

    def configure(self, **kwargs):
        # Add the yapp binary
        self.configureEnvironment["PATH"] = os.getenv("PATH") + ":" + str(Path(shutil.which("perl")).resolve().parent)
        super().configure(cwd=self.source_dir, **kwargs)

    def compile(self, **kwargs):
        if SMB_OUT_OF_SOURCE_BUILD_WORKS:
            self.run_make("build", cwd=self.source_dir)
        else:
            super().compile(**kwargs)

    def install(self, **kwargs):
        if SMB_OUT_OF_SOURCE_BUILD_WORKS:
            self.run_make("install", cwd=self.source_dir)
        else:
            super().install(**kwargs)

    def process(self):
        if OSInfo.IS_MAC:
            # We need readline and krb5 from homebrew:
            with set_env(PATH="/usr/local/opt/krb5/bin:/usr/local/opt/krb5/sbin:" + os.getenv("PATH", ""),
                         PKG_CONFIG_PATH="/usr/local/opt/krb5/lib/pkgconfig:/usr/local/opt/readline/lib/pkgconfig:" +
                                         os.getenv(
                             "PKG_CONFIG_PATH", ""),
                         LDFLAGS="-L/usr/local/opt/krb5/lib -L/usr/local/opt/readline/lib",
                         CPPFLAGS="-I/usr/local/opt/krb5/include -I/usr/local/opt/readline/include",
                         CFLAGS="-I/usr/local/opt/krb5/include -I/usr/local/opt/readline/include"):
                super().process()
        else:
            super().process()

    def needsConfigure(self):
        return True
