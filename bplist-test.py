import sys, os
from pathlib import Path
from tqdm import tqdm
import sqlite3
from shutil import copy
from bpylist import bplist

from sys import argv

if len(argv) > 1:
    with open(argv[1], 'rb') as f :
        parsed = bplist.parse(f.read())
        print(parsed)
        for e in parsed:
            print(e)

else:

    path_to_aplib = Path("/Volumes/lacie-6/hd000/1-JAN FAMILIES/JAN-S FAMILY 2013*Z.aplibrary")
    path_to_aplib = Path("/Volumes/ramdisk/foo/JAN-S FAMILY 2013*Z.aplibrary")

    export_path = Path("/Volumes/ramdisk/")

    con = sqlite3.connect(path_to_aplib / "Database/apdb/BigBlobs.apdb")
    cur = con.cursor()
    for uuid,blob in cur.execute('select uuid, cgImageData from cgImageData'):
        if uuid == '29+ttLtHQliWxJdHcsZHoA':
            parsed = bplist.parse(blob)
            print(parsed)

    
    print()
    print()
    with open('/Volumes/ramdisk/foo/JAN-S FAMILY 2013*Z.aplibrary/Database/Albums/xz6bv4DEQ6izxN52y6qEMw.apalbum' , 'rb') as f :
        parsed = bplist.parse(f.read())
        print(parsed["versionUuids"])
