#!/usr/bin/env python3

#TODO: check that the library is version 3.6
#TODO: accept command line args
#TODO: remove items from parent project if exists in album (optionally)
#TODO: Export generated preview for adjusted photos
#TODO: preserve version name if different from original file name
#TODO: handle referenced photos

import sys, os
from pathlib import Path
#from tqdm import tqdm
import sqlite3
from shutil import copy
from bpylist import bplist


#TODO: make this generic
path_to_aplib = Path("/Users/user/Desktop/JAN-S FAMILY 2013*Z.aplibrary")
export_path = Path("/Users/user/Desktop/")


global VERBOSE
VERBOSE = True
global EXPORT_ALBUMS
EXPORT_ALBUMS = True

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
#uuid --> path of object
global location_of
location_of = {}
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
# Extract info from sqlite tables
################################################

#connect to Library sqlite3 database
con = sqlite3.connect(path_to_aplib / "Database/apdb/Library.apdb")
cur = con.cursor()

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


#From table RKVersion
#information about versions (uuid of corresponding originals)
for uuid,master,raw,nonraw,adjusted in cur.execute('select uuid, masterUuid, rawMasterUuid, nonRawMasterUuid, hasAdjustments from RKVersion'):
    master_set = {master, raw, nonraw}
    master_set.remove(None)
    if len(master_set) > 2:
        raise Exception("More than 2 masters?")
    versions[uuid] = master_set



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
        children_of[uuid] = []
        if parent not in children_of:
            children_of[parent] = []
        children_of[parent].append(uuid)
        albumFilePath = path_to_aplib / "Database/Albums" / (uuid + ".apalbum")
        with open(albumFilePath, "rb") as f:
            parsed = bplist.parse(f.read())

            #TODO: do we need this
            albums[uuid] = parsed["versionUuids"]

            #add the masters as children of the album
            for vuuid in parsed["versionUuids"]:
                children_of[uuid] += list(versions[vuuid])




#add originals to dicts and a list
for uuid,origfname,imagePath,projectUuid in cur.execute('select uuid, originalFileName, imagePath, projectUuid from RKMaster'):
    type_of[uuid] = type_original
    parent_of[uuid] = projectUuid
    name_of[uuid] = origfname

    if projectUuid not in children_of:
        children_of[projectUuid] = []
    children_of[projectUuid].append(uuid)

    #TODO: if in masters folder (within library)
    #Assume photo is managed
    location_of[uuid] = path_to_aplib / "Masters" / imagePath

    #TODO if referenced
        #TODO: if offline
        #TODO: if online


################################################
# Export
################################################

def makeHierarchy(uuid, path):
    #skip albums if the option is set
    if type_of[uuid] == type_album and EXPORT_ALBUMS == False:
        return

    name = name_of[uuid]
    if VERBOSE:
        print(str(path / name))

    if type_of[uuid] in [type_folder, type_project, type_album]:
        try:
            #create a directory
            os.mkdir(path / name)
        except FileExistsError  as e:
            pass
        if uuid not in children_of:
            raise Exception("Folder/Project/Album not in children_of dict!")

        #recurse on each child
        for child in children_of[uuid]:
            makeHierarchy(child, path / name)

    elif type_of[uuid] == type_original:
        #copy original photo
        to_here = path / name
        copy(location_of[uuid], to_here)

    elif type_of[uuid] == type_version:
        for master in versions[uuid]:
            copy(location_of[uuid], path / name)


#TODO: what happens if I make this something higher up?
root_uuid = "AllProjectsItem"
makeHierarchy(root_uuid, export_path)

#generate XMP file if there is worthy metadata
