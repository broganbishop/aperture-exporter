#!/usr/bin/env python3

import sys, os
from pathlib import Path
from tqdm import tqdm
import sqlite3
from shutil import copy
from bpylist import bplist


#TODO: make this generic
path_to_aplib = Path("/Volumes/ramdisk/foo/JAN-S FAMILY 2013*Z.aplibrary")
export_path = Path("/Volumes/ramdisk/")

global folder_paths 
folder_paths = {}

def makeHierarchy(dicts, uuid, path):
    children_of, name_of, parent_of = dicts
    name = name_of[uuid]

    print(str(path / name))
    folder_paths[uuid] = path / name
    try:
        os.mkdir(path / name)
    except FileExistsError  as e:
        pass

    if uuid not in children_of:
        return

    for child in children_of[uuid]:
        makeHierarchy(dicts, child, path / name)



#TODO:possibly copy to ramdisk first

#connect to Library sqlite3 database
con = sqlite3.connect(path_to_aplib / "Database/apdb/Library.apdb")
cur = con.cursor()

#create folder structure (folders, projects, and albums)

#build dicts
children_of = {}
name_of = {}
parent_of = {}
albums = {}
versions = {}

#RKFolder
#This table holds information about all folders and projects (TopLevel stuff too)
for uuid,parent,name in cur.execute('select uuid, parentFolderUuid, name from RKFolder'):
    if parent not in children_of:
        children_of[parent] = []
    children_of[parent].append(uuid)
    name_of[uuid] = name
    parent_of[uuid] = parent



#RKAlbum
#holds info on every album in the aplib (some are built in)
for uuid,subclass,name,parent in cur.execute('select uuid, albumSubclass, name, folderUuid from RKAlbum'):
    if subclass == 3 and uuid != "lastImportAlbum":
        parent_of[uuid] = parent
        name_of[uuid] = name
        if parent not in children_of:
            children_of[parent] = []
        children_of[parent].append(uuid)
        albumFilePath = path_to_aplib / "Database/Albums" / (uuid + ".apalbum")
        with open(albumFilePath, "rb") as f:
            parsed = bplist.parse(f.read())
            albums[uuid] = parsed["versionUuids"]

#RKVersion
for uuid,master,raw,nonraw in cur.execute('select uuid, masterUuid, rawMasterUuid, nonRawMasterUuid from RKVersion'):
    versions[uuid] = {master, raw, nonraw}
    versions[uuid].remove(None)
    print(versions[uuid])

root_uuid = "AllProjectsItem"
makeHierarchy((children_of,name_of,parent_of), root_uuid, export_path)



#add originals to dicts and a list
export_list = []
for row in cur.execute('select uuid, originalFileName, imagePath, projectUuid from RKMaster'):
    uuid,origfname,imagePath,projectUuid = row
    parent_of[uuid] = projectUuid
    name_of[uuid] = origfname
    export_list.append((uuid,imagePath))

#for album_uuid in albums.keys():
    #for photo_uuid in albums[album_uuid]:
        #export_list.append((album_uuid, ph

#export every master + raw into corresponding project or album
for image in export_list:
    copy(path_to_aplib / "Masters" / image[1], folder_paths[parent_of[image[0]]] / name_of[image[0]])


#generate XMP file if there is worthy metadata
