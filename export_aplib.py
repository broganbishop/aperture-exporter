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

#TODO: captions, titles, version name if different from original file name
#TODO: use tqdm
#TODO: children_of should store sets not lists for performance reasons
#TODO: UNIT TESTS
#TODO: switch to a "Version-centric" model of exporting

import sys
import os
from pathlib import Path
#from tqdm import tqdm
import sqlite3
from shutil import copy2
from bpylist import bplist
import hashlib
import plistlib

global VERBOSE
VERBOSE = False
def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)



global EXPORT_ALBUMS
EXPORT_ALBUMS = True
global ECLIPSE
ECLIPSE = True
global EXPORT_ADJUSTED
EXPORT_ADJUSTED = True
global DRY_RUN
DRY_RUN = False
global DIRECTORY_THRESHOLD
DIRECTORY_THRESHOLD = 1000

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
global name_of, original_file_name_of, version_name_of, basename_of, extension_of
name_of = {}
original_file_name_of = {}
version_name_of = {}
basename_of = {}
extension_of = {}
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
global unavailable
unavailable = set()
#
global sha256sum_of
sha256_of = {}
#
global volume
volume = {}
#
global metadata
metadata = {}


def getSHA256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    hash_str = sha256_hash.hexdigest()
    return hash_str

def writeMetadataXMP(uuid, path):
    if uuid not in metadata:
        raise Exception("No metadata to write!")
        return

    if "rating" in metadata[uuid]:
        rating_string = f"\t<xap:Rating>{metadata[uuid]['rating']}</xap:Rating>\n"
    else:
        rating_string = ""

    if "keywords" in metadata[uuid]:
        keyword_string = "\t<dc:subject><rdf:Bag>\n"
        for k in metadata[uuid]["keywords"]:
            keyword_string += f"\t\t<rdf:li>{k}</rdf:li>\n"
        keyword_string += "\t</rdf:Bag></dc:subject>\n"
    else:
        keyword_string = ""

    xmp_data = ("<?xpacket begin='' id=''?>\n"
    "<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='XMP toolkit 2.9-9, framework 1.6'>\n"
    "<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' "
    "xmlns:iX='http://ns.adobe.com/iX/1.0/'>\n"
    "<rdf:Description rdf:about='' "
    "xmlns:Iptc4xmpCore='http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/'>\n"
    "</rdf:Description>\n"
    "<rdf:Description rdf:about='' xmlns:photoshop='http://ns.adobe.com/photoshop/1.0/'>\n"
    "</rdf:Description>\n"
    "<rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/'>\n"
    + keyword_string +
    "</rdf:Description>\n"
    "<rdf:Description rdf:about='' "
    "xmlns:photomechanic='http://ns.camerabits.com/photomechanic/1.0/'>\n"
    "</rdf:Description>\n"
    "<rdf:Description rdf:about='' xmlns:xap='http://ns.adobe.com/xap/1.0/'>\n"
    + rating_string + 
    "</rdf:Description>\n"
    "</rdf:RDF>\n</x:xmpmeta>\n<?xpacket end='w'?>\n")

    if path.exists():
        raise Exception("XMP file exists!!")
    with open(path, "w") as xmp_file:
        xmp_file.write(xmp_data)


########################################################################
# Extract info from sqlite tables
########################################################################

#Check that the aperture lib is upgraded to 3.6
with open(path_to_aplib / "Info.plist", "rb") as info_plist:
    info = plistlib.load(info_plist)
    if info["CFBundleShortVersionString"] != "3.6":
        raise Exception("Aperture Library is not version 3.6! UPGRADE")
    else:
        vprint("Library version 3.6")

#connect to Library sqlite3 database
con = sqlite3.connect(path_to_aplib / "Database/apdb/Library.apdb")
cur = con.cursor()

#From table RKFolder
#This table holds information about all folders and projects
vprint("Reading RKFolder...", end="", flush=True)
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

vprint("done.")

# RKImportGroup
# Date and time of each import group
# (used to store versions/full sized previews)
vprint("Reading RKImportGroup...", end="", flush=True)
for uuid, year, month, day, time in cur.execute(
        'select uuid, importYear, importMonth, importDay, importTime '
        'from RKImportGroup'):
    import_group_path[uuid] = (path_to_aplib / "Database" / "Versions"
            / year / month / day
            / (year + month + day + "-" + time))

vprint("done.")

#RKVolume
#volume info for referenced files
vprint("Reading RKVolume...", end='', flush=True)
for uuid, name in cur.execute(
        'select uuid, name from RKVolume'):
    volume[uuid] = name

vprint("done.")


#RKMaster
#add originals to dicts and a list
vprint("Reading RKMaster...", end='', flush=True)
for uuid, origfname, imagePath, projectUuid, importGroupUuid, isMissing, \
        isRef, vol_uuid, origvname, inTrash in cur.execute(
        'select uuid, originalFileName, imagePath, projectUuid, '
        'importGroupUuid, isMissing, fileIsReference, fileVolumeUuid, '
        'originalVersionName, isInTrash '
        'from RKMaster'):
    type_of[uuid] = type_original
    if inTrash == 1:
        projectUuid = "TrashFolder"
    parent_of[uuid] = projectUuid
    import_group[uuid] = importGroupUuid
    if origfname == None:
        raise Exception("No original file name. REBUILD DATABASE!")

    if "." in origfname:
        ext,basename = origfname[::-1].split(".", 1)
        ext,basename = ("." + ext[::-1]),basename[::-1]
        basename_of[uuid] = basename
        extension_of[uuid] = ext
        name_of[uuid] = basename + ext
    else:
        print(origfname)
        raise Exception("No file extention!")

    if projectUuid not in children_of:
        children_of[projectUuid] = []

    if isRef == 0:
        fullImagePath = path_to_aplib / "Masters" / imagePath
    elif isRef == 1:
        fullImagePath = Path("/Volumes") / volume[vol_uuid] / imagePath 

    #If the file is present, then add it to be exported
    if fullImagePath.exists() and fullImagePath.is_file():
        if isMissing == 1:
            raise Exception("File 'Missing' but exists!")
        #sha256_of[uuid] = getSHA256(fullImagePath)
        #truncated_hash = ("{sha256+" + sha256_of[uuid][:8] + "}")[::-1]
        location_of[uuid] = fullImagePath
        children_of[projectUuid].append(uuid)

    else:
        unavailable.add(uuid)
    
vprint("done.")

def addMetadata(uuid, key, data):
    if uuid not in metadata:
        metadata[uuid] = {}

    if key == "keywords":
        if "keywords" not in metadata[uuid]:
            metadata[uuid]["keywords"] = set()
        metadata[uuid]["keywords"] |= set(map(str.strip, data))

    elif key == "rating":
        if "rating" not in metadata[uuid]:
            metadata[uuid]["rating"] = data
        else:
            raise Exception("Multiple Ratings")
            metadata[uuid]["rating"] = max(metadata[uuid]["rating"], data)

    else:
        if key in metadata[uuid]:
            print(uuid, key, data)
            raise Exception("Key already in metadata")
        else:
            metadata[uuid][key] = data

    


#From table RKVersion
#information about versions (uuid of corresponding originals)
vprint("Reading RKVersion...", end='', flush=True)
for uuid, name, master, raw, nonraw, adjusted, versionNum, mainRating,\
        hasKeywords in cur.execute(
        'select uuid, name, masterUuid, rawMasterUuid, nonRawMasterUuid, '
        'hasEnabledAdjustments, versionNumber, mainRating, hasKeywords '
        'from RKVersion'):
    version_file = (import_group_path[import_group[master]] / master /
            ("Version-" + str(versionNum) + ".apversion"))

    caption = None
    title = None
    if versionNum > 0:
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
                if ("iptcProperties" in parsed and "Keywords" in parsed["iptcProperties"]):
                    keywords = parsed["iptcProperties"]["Keywords"].split(",") #Strip whitespace?
                elif "keywords" in parsed:
                    keywords = parsed["keywords"]
                else:
                    raise Exception("No keywords??")
            if "iptcProperties" in parsed:
                if "Caption/Abstract" in parsed["iptcProperties"]:
                    caption = parsed["iptcProperties"]["Caption/Abstract"]
                if "ObjectName" in parsed["iptcProperties"]:
                    title = parsed["iptcProperties"]["ObjectName"]

    type_of[uuid] = type_version
    basename_of[uuid] = name
    extension_of[uuid] = ".jpg"
    name_of[uuid] = name + ".jpg" #TODO: preserve original file name
    master_of[uuid] = master
    master_set = {raw, nonraw}
    if None in master_set:
        master_set.remove(None)
    all_masters_of[uuid] = master_set

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
        uuids = []
        if adjusted:
            uuids.append[uuid]
        uuids += list(all_masters_of[uuid])
        for item in uuids:
            addMetadata(item, "keywords", keywords)


    if mainRating != 0:
        uuids = []
        if adjusted == 1:
            uuids = [uuid]
        else:
            uuids = list(all_masters_of[uuid])
        for item in uuids:
            addMetadata(item, "rating", mainRating)

    if caption != None:
        #TODO: this is wrong
        addMetadata(uuid, "caption", caption)

vprint("done.")

        


#From table RKAlbum
#holds info on every album in the aplib (some are built in)
vprint("Reading RKAlbum...", end='', flush=True)
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
                        if current_uuid not in type_of:
                            break
                        elif type_of[current_uuid] == type_project:
                            parent_project = current_uuid
                            break
                        elif current_uuid == "AllProjectsItem":
                            break

                #add the masters as children of the album
                for vuuid in parsed["versionUuids"]:
                    for master in all_masters_of[vuuid]:
                        if master not in unavailable:
                            children_of[uuid].append(master)

                    # if the ECLIPSE option is set, 
                    # remove items from the parental project
                    # if they exist there to prevent duplication
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

vprint("done.")


################################################
# Pre-Export Sanity Checks
################################################

for uuid in children_of.keys():
    if len(children_of[uuid]) > DIRECTORY_THRESHOLD:
        print(name_of[uuid] + ": " + len(children_of[uuid]))
        raise Exception("Warning! There are many items")

vprint("Passed sanity checks.")

################################################
# Export
################################################

def export(uuid, path):

    if EXPORT_ALBUMS == False:
        if type_of[uuid] == type_album:
            return

    if type_of[uuid] in [type_folder, type_project, type_album]:
        #skip empty directories
        #if uuid not in children_of or len(children_of[uuid]) == 0:
            #return
        vprint(str(path / name_of[uuid]))
        if DRY_RUN == False:
            os.mkdir(path / name_of[uuid]) #create a directory

        #sort the children so that directories come first
        for child in sorted(children_of[uuid], key=lambda c: type_of[c]):
            export(child, path / name_of[uuid]) #recurse on each child

    elif type_of[uuid] == type_original or (type_of[uuid] == type_version 
            and EXPORT_ADJUSTED):

        #don't overwrite files of the same name
        counter = 0
        while (path / name_of[uuid]).exists():
            counter += 1
            counter_str = " (" + str(counter) + ")"
            name_of[uuid] = basename_of[uuid] + counter_str + extension_of[uuid]

        vprint(str(path / name_of[uuid]))
        if DRY_RUN == False:
            copy2(location_of[uuid], path / name_of[uuid])
            if uuid in metadata:
                vprint(metadata[uuid])
                writeMetadataXMP(uuid, path / (name_of[uuid] + ".xmp"))

#Exclude some junk
exclude_if_empty = ['TopLevelBooks', 'TopLevelAlbums', 'TopLevelKeepsakes', 'TopLevelSlideshows',
        'TopLevelWebProjects', 'TopLevelLightTables', 'PublishedProjects', 'TrashFolder']
for uuid in exclude_if_empty:
    if len(children_of[uuid]) == 0:
        children_of[parent_of[uuid]].remove(uuid)

root_uuid = "LibraryFolder"
name_of["LibraryFolder"] = path_to_aplib.name + ".exported"
name_of["TopLevelAlbums"] = "Albums"
export(root_uuid, export_path)

