#!/usr/bin/env python3
"""Mac side: copy the full-res player crops into the library (Portraits/Action/_Unidentified Photos).
copy_photos.py <crops dir> <lib_plan.json> <library dir>"""
import sys, os, json, shutil
if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):   # usage before anything runs
    print(__doc__); sys.exit(0)
crops, plan, lib = sys.argv[1:4]; n = 0
for x in json.load(open(plan)):
    dst = os.path.join(lib, x['dst']); os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) and os.path.exists(os.path.join(crops, x['src'])): shutil.copy(os.path.join(crops, x['src']), dst); n += 1
print('copied', n)
