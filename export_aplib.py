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

#TODO: check that the library is version 3.6
#TODO: preserve version name if different from original file name
#TODO: check for overwriting existing files exporting two photos w/ same name
#TODO: use tqdm
#TODO: check for folders with insane numbers of photos (1000+)
#TODO: generate XMP file if there is worthy metadata
#TODO: export trash?
#TODO: children of should store sets not lists for performance reasons
#TODO: Currently this exports "AllProjectsItem". should we export more?
#TODO: UNIT TESTS
#TODO: switch to a "Version-centric" model of exporting

import sys
import os
from pathlib import Path
#from tqdm import tqdm
import sqlite3
from shutil import copy
from bpylist import bplist

global VERBOSE
VERBOSE = False
global EXPORT_ALBUMS
EXPORT_ALBUMS = True
global ECLIPSE
ECLIPSE = True
global EXPORT_ADJUSTED
EXPORT_ADJUSTED = True
global DRY_RUN
DRY_RUN = False

global type_folder, type_project, type_album, type_original, type_version
type_folder = 1
type_project = 2
type_album = 3
type_original = 4
type_version = 5

########################################################################
# handle command line arguments
########################################################################
del sys.argv[0]
args = sys.argv
if '--dry-run' in args:
    DRY_RUN = True
    args.remove("--dry-run")
if '--no-albums' in args:
    EXPORT_ALBUMS = False
    ECLIPSE = False
    args.remove("--no-albums")
if '--no-cover' in args:
    ECLIPSE = False
    args.remove("--no-cover")
if '--verbose' in args:
    VERBOSE = True
    args.remove("--verbose")
if '--no-adjusted' in args:
    EXPORT_ADJUSTED = False
    args.remove("--no-adjusted")
if len(args) != 2:
    raise Exception(
            "Invalid number of args! ([--options], aplib, export_location)")
path_to_aplib = Path(args[0])
export_path = Path(args[1])


########################################################################
# Define dictionaries
########################################################################
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
#version --> full size preview
#master --> original photo
global location_of
location_of = {}
#
# uuid (version) --> uuid(s) of originals (set) TODO make this a tuple?
global all_masters_of
all_masters_of = {}
#
# uuid (version) --> master uuid
global master_of
master_of = {}
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
global keywords_of
keywords_of = {}
#
global rating
rating = {}
#
global unavailable
unavailable = set()


########################################################################
# Extract info from sqlite tables
########################################################################

#connect to Library sqlite3 database
con = sqlite3.connect(path_to_aplib / "Database/apdb/Library.apdb")
cur = con.cursor()

#From table RKFolder
#This table holds information about all folders and projects
for uuid, parent, name, folderType in cur.execute(
        'select uuid, parentFolderUuid, name, folderType '
        'from RKFolder'):
    if uuid not in children_of:
        children_of[uuid] = []
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
    elif folderType == 3: #Same as 1?
        type_of[uuid] = type_folder
    else:
        raise Exception("Item in RKFolder has undefined type!")

# RKImportGroup
# Date and time of each import group
# (used to store versions/full sized previews)
for uuid, year, month, day, time in cur.execute(
        'select uuid, importYear, importMonth, importDay, importTime '
        'from RKImportGroup'):
    import_group_path[uuid] = (path_to_aplib / "Database" / "Versions"
            / year / month / day
            / (year + month + day + "-" + time))


#RKMaster
#add originals to dicts and a list
for uuid, origfname, imagePath, projectUuid, importGroupUuid, isMissing, \
        isRef in cur.execute(
        'select uuid, originalFileName, imagePath, projectUuid, '
        'importGroupUuid, isMissing, fileIsReference '
        'from RKMaster'):
    type_of[uuid] = type_original
    parent_of[uuid] = projectUuid
    if origfname == None:
        raise Exception("No original file name. REBUILD DATABASE!")
    name_of[uuid] = origfname
    import_group[uuid] = importGroupUuid


    if projectUuid not in children_of:
        children_of[projectUuid] = []

    #TODO:
    location_of[uuid] = path_to_aplib / "Masters" / imagePath

    #TODO: acctually check whether the file exists instead of asking the db
    #If the file is present, then add it to be exported
    if isMissing != 1 and isRef != 1: #imperfect proxy for the above
        location_of[uuid] = path_to_aplib / "Masters" / imagePath
        children_of[projectUuid].append(uuid)
    elif isRef == 1:
        #TODO: implement logic for referenced files
        #check if photo is present
        #add location (including Volume)
        #add it to the hierarchy
        pass
    
    if isMissing == 1 or isRef == 1:
        unavailable.add(uuid)



#From table RKVersion
#information about versions (uuid of corresponding originals)
for uuid, name, master, raw, nonraw, adjusted, versionNum, mainRating,\
        hasKeywords in cur.execute(
        'select uuid, name, masterUuid, rawMasterUuid, nonRawMasterUuid, '
        'hasEnabledAdjustments, versionNumber, mainRating, hasKeywords '
        'from RKVersion'):
    version_file = (import_group_path[import_group[master]] / master /
            ("Version-" + str(versionNum) + ".apversion"))
    with open(version_file, 'rb') as f :
        parsed = bplist.parse(f.read())
        if "imageProxyState" in parsed:
            upToDate = parsed["imageProxyState"]["fullSizePreviewUpToDate"]
        else:
            raise Exception("No imageProxyState! GENERATE PREVIEWS")
        if adjusted:
            previewPath = (path_to_aplib / "Previews"
                    / parsed["imageProxyState"]["fullSizePreviewPath"])
        if hasKeywords == 1:
            #TODO
            if "Keywords" in parsed["iptcProperties"]:
                keywords = parsed["iptcProperties"]["Keywords"] #type string
            else:
                keywords = parsed["iptcProperties"] #SpecialInstructions???
            keywords = parsed["keywords"] #type list

    if adjusted == 1:
        adjusted_photos.add(uuid)

        # Find the path to full size preview
        # add version uuid as child of project
        #TODO: this is partly wrong
        #       (an adjusted version might not sit with its master)
        #(might have to handle implicit albums to do this right)
        if upToDate != True:
            raise Exception("Preview not up to date!")
        location_of[uuid] = previewPath
        children_of[parent_of[master]].append(uuid)

    if hasKeywords == 1:
        #TODO: should these go to the master
        #when photo is adjusted? when photo isn't?
        keywords_of[uuid] = keywords
        #print("Found keywords: " + str(keywords))

    if mainRating != 0:
        #TODO
        rating[uuid] = mainRating
        #print("Found rating: " + str(mainRating))

    type_of[uuid] = type_version
    name_of[uuid] = name + ".jpg" #TODO: preserve original file name
    master_of[uuid] = master
    master_set = {raw, nonraw}
    master_set.remove(None)
    all_masters_of[uuid] = master_set


#From table RKAlbum
#holds info on every album in the aplib (some are built in)
for uuid, albumType, subclass, name, parent in cur.execute(
        'select uuid, albumType, albumSubclass, name, folderUuid '
        'from RKAlbum'):
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

                #determine parent project if any
                parent_project = None
                if ECLIPSE == True:
                    current_uuid = uuid
                    while type_of[current_uuid] != type_project:
                        current_uuid = parent_of[current_uuid]
                        if type_of[current_uuid] == type_project:
                            parent_project = current_uuid
                        elif current_uuid == "AllProjectsItem":
                            break

                #add the masters as children of the album
                for vuuid in parsed["versionUuids"]:
                    for master in all_masters_of[vuuid]:
                        if master not in unavailable:
                            children_of[uuid].append(master)

                    # if the ECLIPSE option is set, 
                    # remove items from the parental project
                    # if the exist there to prevent duplication
                    if ECLIPSE == True and parent_project != None:
                        for item in [vuuid] + list(all_masters_of[vuuid]):
                            try:
                                children_of[parent_project].remove(item)
                            except ValueError as e:
                                pass
                    #if photo is adjusted, add it as a child of the album
                    #TODO (this does not handle projects)
                    if vuuid in adjusted_photos:
                        children_of[uuid].append(vuuid)
        except RuntimeError as e:
            print("Unable to parse: " + str(albumFilePath) + " ("
                    + name_of[uuid] + ")")
            raise e



################################################
# Export
################################################

def export(uuid, path):
    path = path / name_of[uuid]

    if EXPORT_ALBUMS == False:
        if type_of[uuid] == type_album:
            return

    if VERBOSE:
        print(str(path))

    if type_of[uuid] in [type_folder, type_project, type_album]:
        try:
            if DRY_RUN == False:
                os.mkdir(path) #create a directory
        except FileExistsError as e:
            pass

        for child in children_of[uuid]:
            export(child, path) #recurse on each child

    elif type_of[uuid] == type_original:
        if DRY_RUN == False:
            copy(location_of[uuid], path) #copy original

    elif type_of[uuid] == type_version and EXPORT_ADJUSTED:
        if DRY_RUN == False:
            copy(location_of[uuid], path) #copy preview


root_uuid = "AllProjectsItem"
export(root_uuid, export_path)

