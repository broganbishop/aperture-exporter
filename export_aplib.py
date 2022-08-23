#!/usr/bin/env python3

#Things to be done to library before running this program:
# Upgrade to 3.6
# may want to repair or rebuild library...
# reconnect and consolidate  all referenced photos
# Adjust previews to full-size (no limit) quality 10
# Regenerate previews for adjusted photos
#       (on compatible os! [black version problem])
# verify the status of all photos
#       (update isMissing for photos that are offline)

#TODO: use tqdm
#TODO: UNIT TESTS
#TODO: remove bad characters from names

import sys
import os
import re
from pathlib import Path
#from tqdm import tqdm

from aperture import Aplib

import settings
settings.init()

from utils import getSHA256
from utils import AlreadyExportedException

settings.options["VERBOSE"] = False
settings.options["EXPORT_ALBUMS"] = True
settings.options["ECLIPSE"] = True
settings.options["EXPORT_ADJUSTED"] = True
settings.options["DRY_RUN"] = False
settings.options["DIRECTORY_THRESHOLD"] = 20000
settings.options["STRICT_PREVIEW_CHECK"] = True


########################################################################
# handle command line arguments
########################################################################
del sys.argv[0]
args = sys.argv
if '--dry-run' in args:
    settings.options["DRY_RUN"] = True
    args.remove("--dry-run")
if '--no-albums' in args:
    settings.options["EXPORT_ALBUMS"] = False
    settings.options["ECLIPSE"] = False
    args.remove("--no-albums")
if '--no-cover' in args:
    settings.options["ECLIPSE"] = False
    args.remove("--no-cover")
if '--verbose' in args:
    settings.options["VERBOSE"] = True
    args.remove("--verbose")
if '--no-adjusted' in args:
    settings.options["EXPORT_ADJUSTED"] = False
    args.remove("--no-adjusted")
if '--no-strict-preview-check' in args:
    settings.options["STRICT_PREVIEW_CHECK"] = False
    args.remove("--no-strict-preview-check")
if len(args) != 2:
    raise Exception("Invalid number of args! ([--options], aplib, export_location)")

path_to_aplib = Path(args[0])
export_path = Path(args[1])

pattern = re.compile(".*\.aplibrary$")
aplibs = []
for dirpath, dirnames, filenames in os.walk(path_to_aplib):
    to_remove = []
    for d in dirnames:
        match = pattern.fullmatch(d)
        if pattern.fullmatch(d) != None:
            aplibs.append((dirpath, d))#tuple
            to_remove.append(d)
    for d in to_remove:
        dirnames.remove(d)

for lib in aplibs:
    lib_path = Path(lib[0]) / lib[1]
    print()
    print(str(lib_path))
    mod_xprt_path = Path(str(lib[0]).replace(str(path_to_aplib), str(export_path), 1))
    os.makedirs(mod_xprt_path, exist_ok=True)
    try:
        #Create Aperture Library Object
        ap = Aplib(lib_path, mod_xprt_path)
        ap.export()
    except AlreadyExportedException as e:
        pass
    except Exception as e:
        print("Exception1!")
        print(lib_path)
        print(str(e))


