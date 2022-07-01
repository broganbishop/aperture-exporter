#!/usr/bin/env python3

#TODO: check that the library is version 3.6
#TODO: preserve version name if different from original file name
#TODO: handle referenced photos

#TODO: children of should store sets not lists for performance reasons

import sys, os
from pathlib import Path
#from tqdm import tqdm
import sqlite3
from shutil import copy
from bpylist import bplist

global VERBOSE
VERBOSE = False
global EXPORT_ALBUMS
EXPORT_ALBUMS = True
global ALBUM_CHILDREN_COVER_PARENT_PROJECT  
ALBUM_CHILDREN_COVER_PARENT_PROJECT = True
global DRY_RUN
DRY_RUN = False

global type_undefined, type_folder, type_project, type_album, type_original, type_version
type_undefined = 0
type_folder = 1
type_project = 2
type_album = 3
type_original = 4
type_version = 5

################################################
# handle command line arguments
################################################

del sys.argv[0]
args = sys.argv

if '--dry-run' in args:
    DRY_RUN = True
    args.remove("--dry-run")

if '--no-albums' in args:
    EXPORT_ALBUMS = False
    ALBUM_CHILDREN_COVER_PARENT_PROJECT = False
    args.remove("--no-albums")

if '--no-cover' in args:
    ALBUM_CHILDREN_COVER_PARENT_PROJECT = False
    args.remove("--no-cover")

if '--verbose' in args:
    VERBOSE = True
    args.remove("--verbose")

if len(args) != 2:
    raise Exception("Invalid number of args! ([options], aplib, export location)")


path_to_aplib = Path(args[0])
export_path = Path(args[1])


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
#
# uuid (version) --> version number
global version_number
version_number = {}
#
#list of uuids (versions that have adjustments)
global adjusted_photos
adjusted_photos = set()
#
#import group uuid --> path (to version info)
global import_group_path
import_group_path = {}
#
#master uuid --> import group uuid
global import_group
import_group = {}
#
global is_missing
is_missing = set()
#
global is_reference
is_reference = set()


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
    children_of[uuid] = []
    if folderType == 1:
        type_of[uuid] = type_folder
    elif folderType == 2:
        type_of[uuid] = type_project
        children_of[uuid] = []
    elif folderType == 3: #TODO: should this be treated differently than 1?
        type_of[uuid] = type_folder
    else:
        raise Exception("Item in RKFolder has undefined type!")
        type_of[uuid] = type_undefined

#RKImportGroup
#Date and time of each import group (used to store versions/full sized previews)
for uuid,year,month,day,time in cur.execute('select uuid, importYear, importMonth, importDay, importTime from RKImportGroup'):
    path = path_to_aplib / "Database" / "Versions" / year / month / day / (year + month + day + "-" + time)
    import_group_path[uuid] = path


#RKMaster
#add originals to dicts and a list
for uuid,origfname,imagePath,projectUuid,importGroupUuid,isMissing,isRef in cur.execute('select uuid, originalFileName, imagePath, projectUuid, importGroupUuid, isMissing, fileIsReference from RKMaster'):
    type_of[uuid] = type_original
    parent_of[uuid] = projectUuid
    name_of[uuid] = origfname
    import_group[uuid] = importGroupUuid

    if isMissing == 1:
        is_missing.add(uuid)
    if isRef == 1:
        is_reference.add(uuid)

    if projectUuid not in children_of:
        children_of[projectUuid] = []
    children_of[projectUuid].append(uuid)

    #TODO: if in masters folder (within library)
    #Assume photo is managed
    location_of[uuid] = path_to_aplib / "Masters" / imagePath

    #TODO if referenced
        #TODO: if offline
        #TODO: if online


#From table RKVersion
#information about versions (uuid of corresponding originals)
for uuid,name,master,raw,nonraw,adjusted,versionNum in cur.execute('select uuid, name, masterUuid, rawMasterUuid, nonRawMasterUuid, hasEnabledAdjustments, versionNumber from RKVersion'):
    if adjusted == 1:
        adjusted_photos.add(uuid)

        #add version uuid as child of project
        #TODO: this is partly wrong (an adjusted version might not sit with its master)
        #(might have to handle implicit albums to do this right)
        children_of[parent_of[master]].append(uuid)

    type_of[uuid] = type_version
    name_of[uuid] = name #TODO: preserve original file name
    version_number[uuid] = versionNum
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
        try:
            with open(albumFilePath, "rb") as f:
                parsed = bplist.parse(f.read())

                #TODO: do we need this
                albums[uuid] = parsed["versionUuids"]

                #determine parent project if any
                parent_project = None
                if ALBUM_CHILDREN_COVER_PARENT_PROJECT == True:
                    current_uuid = uuid
                    while type_of[current_uuid] != type_project:
                        current_uuid = parent_of[current_uuid]
                        if type_of[current_uuid] == type_project:
                            parent_project = current_uuid
                        elif current_uuid == "AllProjectsItem":
                            break

                #add the masters as children of the album
                for vuuid in parsed["versionUuids"]:
                    children_of[uuid] += list(versions[vuuid])

                    #if the option is set, remove items from 
                    if ALBUM_CHILDREN_COVER_PARENT_PROJECT == True and parent_project != None:
                        for item in [vuuid] + list(versions[vuuid]):
                            try:
                                children_of[parent_project].remove(item)
                            except ValueError as e:
                                pass
                    #if photo is adjusted, add it as a child of the album #TODO (this does not handle projects)
                    if vuuid in adjusted_photos:
                        children_of[uuid].append(vuuid)
        except RuntimeError as e:
            print("Unable to parse: " + str(albumFilePath) + " (" + name_of[uuid] + ")")
            pass



################################################
# Export
################################################

def export(uuid, path):
    #skip albums if the option is set
    if type_of[uuid] == type_album and EXPORT_ALBUMS == False:
        return

    name = name_of[uuid]
    if VERBOSE:
        print(str(path / name))

    if type_of[uuid] in [type_folder, type_project, type_album]:
        try:
            if DRY_RUN == False:
                #create a directory
                os.mkdir(path / name)
        except FileExistsError  as e:
            pass
        if uuid not in children_of:
            print(uuid)
            print(name_of[uuid])
            print(type_of[uuid])
            raise Exception("Folder/Project/Album not in children_of dict!")

        #recurse on each child
        for child in children_of[uuid]:
            export(child, path / name)

    elif type_of[uuid] == type_original:
        if DRY_RUN == False:
            #if the photo is not a reference or missing (TODO how trustworthy are these entries?)
            if uuid not in is_reference and uuid not in is_missing:
                to_here = path / name
                #copy original photo
                copy(location_of[uuid], to_here)

    elif type_of[uuid] == type_version:

        #TODO: if there are two masters (ex: raw + jpg) this is a coin flip
        master = list(versions[uuid])[0]

        version_file = import_group_path[import_group[master]]  / master / ("Version-" + str(version_number[uuid]) + ".apversion")
        with open(version_file, 'rb') as f :
            parsed = bplist.parse(f.read())
            upToDate = parsed["imageProxyState"]["fullSizePreviewUpToDate"]
            previewPath = path_to_aplib / "Previews"/ parsed["imageProxyState"]["fullSizePreviewPath"]

        if upToDate != True:
            raise Exception("Preview not up to date!")
        if DRY_RUN == False:
            to_here = path / name
            copy(previewPath, to_here)


#TODO: what happens if I make this something higher up?
root_uuid = "AllProjectsItem"
export(root_uuid, export_path)

#TODO: generate XMP file if there is worthy metadata
