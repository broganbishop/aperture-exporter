#!/usr/bin/env python3

import sys, os
from pathlib import Path
#from tqdm import tqdm
import sqlite3
from shutil import copy
from bpylist import bplist


#TODO: make this generic
path_to_aplib = Path("/Users/user/Desktop/JAN-S FAMILY 2013*Z.aplibrary")
export_path = Path("/Users/user/Desktop/")

path_to_aplib = Path("/Volumes/SanDisk 32/JAN-S FAMILY 2013*Z.aplibrary")


global VERBOSE
VERBOSE = True

global folder_paths 
folder_paths = {}

global type_undefined
type_undefined = 0
global type_folder
type_folder = 1
global type_project
type_project = 2
global type_album
type_album = 3
global type_original
type_original = 4
global type_version 
type_version = 5


def makeHierarchy(uuid, path):
    name = name_of[uuid]

    if VERBOSE:
        print(str(path / name))

    if type_of[uuid] in [type_folder, type_project, type_album]:
        folder_paths[uuid] = path / name
        try:
            os.mkdir(path / name)
        except FileExistsError  as e:
            pass

        if uuid not in children_of:
            return

        for child in children_of[uuid]:
            makeHierarchy(child, path / name)



#connect to Library sqlite3 database
con = sqlite3.connect(path_to_aplib / "Database/apdb/Library.apdb")
cur = con.cursor()

################################################
#define dictionaries
################################################
# uuid -- type of object (integer defined above)
global type_of
type_of = {}
#
#uuid (parent) -- list of uuids (children)
global children_of
children_of = {}
#
#uuid -- name of thing (string)
global name_of
name_of = {}
#
#uuid (child) -- uuid (parent)
global parent_of
parent_of = {}
#
#dictionary for albums
#uuid (album) -- list of uuids (versions in album)
global albums
albums = {}
#
# uuid (version) --> uuid(s) of originals
global versions
versions = {}



################################################
# Begin extracting info from library sqlite tables
################################################

#From table RKFolder
#This table holds information about all folders and projects (TopLevel stuff too)
for uuid,parent,name,folderType in cur.execute('select uuid, parentFolderUuid, name, folderType from RKFolder'):
    if parent not in children_of:
        children_of[parent] = []
    children_of[parent].append(uuid)
    name_of[uuid] = name
    parent_of[uuid] = parent
    if folderType == 1:
        type_of[uuid] = type_folder
    elif folderType == 2:
        type_of[uuid] = type_project
        children_of[uuid] = []
    else:
        raise Exception("Item in RKFolder has undefined type!")
        type_of[uuid] = type_undefined


#From table RKAlbum
#holds info on every album in the aplib (some are built in)
for uuid,albumType,subclass,name,parent in cur.execute('select uuid, albumType, albumSubclass, name, folderUuid from RKAlbum'):
    if albumType != 1:
        raise Exception("Album type not 1")
    #these seem to be the only albums that are important
    if albumType == 1 and subclass == 3 and uuid != "lastImportAlbum":
        type_of[uuid] = type_album
        parent_of[uuid] = parent
        name_of[uuid] = name
        if parent not in children_of:
            children_of[parent] = []
        children_of[parent].append(uuid)
        albumFilePath = path_to_aplib / "Database/Albums" / (uuid + ".apalbum")
        with open(albumFilePath, "rb") as f:
            parsed = bplist.parse(f.read())
            albums[uuid] = parsed["versionUuids"]


#From table RKVersion
#information about versions (uuid of corresponding originals)
for uuid,master,raw,nonraw,adjusted in cur.execute('select uuid, masterUuid, rawMasterUuid, nonRawMasterUuid, hasAdjustments from RKVersion'):
    master_set = {master, raw, nonraw}
    master_set.remove(None)
    if len(master_set) > 2:
        raise Exception("More than 2 masters?")
    versions[uuid] = master_set







#TODO: what happens if I make this something higher up?
root_uuid = "AllProjectsItem"
#create folder structure (folders, projects, and albums)
makeHierarchy(root_uuid, export_path)



#add originals to dicts and a list
export_list = []
for uuid,origfname,imagePath,projectUuid in cur.execute('select uuid, originalFileName, imagePath, projectUuid from RKMaster'):
    parent_of[uuid] = projectUuid
    name_of[uuid] = origfname

    if uuid not in children_of:
        children_of[projectUuid] = []
    children_of[projectUuid] += uuid

    #TODO: depricate this export list
    export_list.append((uuid,imagePath))

#for album_uuid in albums.keys():
    #for photo_uuid in albums[album_uuid]:
        #export_list.append((album_uuid, ph

#export every master + raw into corresponding project or album
for image in export_list:
    from_here = path_to_aplib / "Masters" / image[1]
    to_here = folder_paths[parent_of[image[0]]] / name_of[image[0]]
    if VERBOSE:
        print(to_here)
    copy(from_here, to_here)


#generate XMP file if there is worthy metadata
