#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Print phandle -> node path, sorted by phandle value."""
import sys
import fdtlib as F

root = F.load(sys.argv[1])
m = F.phandle_map(root)
for k in sorted(m):
    print("%5d %s" % (k, m[k]))
