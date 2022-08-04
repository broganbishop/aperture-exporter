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
#TODO: make object oriented; lose global vars

#TODO: remove bad characters from names

import sys
import os
from pathlib import Path
#from tqdm import tqdm
import sqlite3
from shutil import copy2
#from bpylist import bplist
import hashlib
import plistlib
from datetime import datetime

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
DIRECTORY_THRESHOLD = 10000
global STRICT_PREVIEW_CHECK
STRICT_PREVIEW_CHECK = True

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
if '--no-strict-preview-check' in args:
    STRICT_PREVIEW_CHECK = False
    args.remove("--no-strict-preview-check")
if len(args) != 2:
    raise Exception("Invalid number of args! ([--options], aplib, export_location)")
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
# uuid (version) --> uuid(s) of originals (set)
# todo: better as a tuple?
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

    if "caption" in metadata[uuid]:
        caption_string = "\t<dc:description><rdf:Alt><rdf:li xml:lang='x-default'>"
        caption_string += metadata[uuid]["caption"]
        caption_string += "</rdf:li></rdf:Alt></dc:description>\n"
    else:
        caption_string = ""

    if "title" in metadata[uuid]:
        title_string = "\t<dc:title><rdf:Alt><rdf:li xml:lang='x-default'>"
        title_string += metadata[uuid]["title"]
        title_string += "</rdf:li></rdf:Alt></dc:title>\n"
    else:
        title_string = ""

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
    + caption_string + keyword_string + title_string +
    "</rdf:Description>\n"
    "<rdf:Description rdf:about='' "
    "xmlns:photomechanic='http://ns.camerabits.com/photomechanic/1.0/'>\n"
    "</rdf:Description>\n"
    "<rdf:Description rdf:about='' xmlns:xap='http://ns.adobe.com/xap/1.0/'>\n"
    + rating_string + 
    "</rdf:Description>\n"
    "</rdf:RDF>\n</x:xmpmeta>\n<?xpacket end='w'?>\n")

    h = None
    if path.exists():
        with open(path, "r") as xmp_file:
            h_file = xmp_file.read()
        h = getSHA256(path)
        #raise Exception("XMP file exists!!")
    with open(path, "w") as xmp_file:
        xmp_file.write(xmp_data)
    if h != None:
        g = getSHA256(path)
        if h != g:
            print(h_file)
            print(xmp_data)
            raise Exception("Overwrote xmp file; hash differs; see above output")




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


#From table RKAdminData
#general info about library
vprint("Reading RKAdminData...", flush=True)
for area, name, value in cur.execute(
        'select propertyArea, propertyName, propertyValue from RKAdminData'):
    if area == "database":
        if name == "databaseUuid":
            vprint("database uuid = ", value)
        elif name == "previewSizeLimit":
            value = int(value)
            vprint("previewSizeLimit =", value)
            previewSizeLimit = value
        elif name == "previewQuality":
            value = round(float(value) * 12)
            vprint("previewQuality =", value)
            previewQuality = value
vprint("done.")


#From table RKFolder
#This table holds information about all folders and projects
vprint("Reading RKFolder...", end="", flush=True)
for uuid, parent, name, folderType in cur.execute(
        'select uuid, parentFolderUuid, name, folderType from RKFolder'):
    if uuid not in children_of:
        children_of[uuid] = set()
    if parent not in children_of:
        children_of[parent] = set()
    children_of[parent].add(uuid)
    if "/" in name:
        #TODO: problems with name mashing
        name = name.replace("/", "-")
    if ":" in name:
        name = name.replace(":", "-")
    name_of[uuid] = name
    parent_of[uuid] = parent

    if folderType == 1:
        type_of[uuid] = type_folder
    elif folderType == 2:
        type_of[uuid] = type_project
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
        'select uuid, importYear, importMonth, importDay, importTime from RKImportGroup'):
    import_group_path[uuid] = (path_to_aplib / "Database" / "Versions"
            / year / month / day / (year + month + day + "-" + time))
vprint("done.")


#RKVolume
#volume info for referenced files
vprint("Reading RKVolume...", end='', flush=True)
for uuid, name in cur.execute('select uuid, name from RKVolume'):
    volume[uuid] = name
vprint("done.")



#RKMaster
#add originals to dicts and a list
vprint("Reading RKMaster...", end='', flush=True)
for uuid, origfname, imagePath, projectUuid, importGroupUuid, isMissing, \
        isRef, vol_uuid, origvname, inTrash in cur.execute(
        'select uuid, originalFileName, imagePath, projectUuid, importGroupUuid, isMissing, '
        'fileIsReference, fileVolumeUuid, originalVersionName, isInTrash from RKMaster'):
    type_of[uuid] = type_original
    if inTrash == 1:
        projectUuid = "TrashFolder"
    parent_of[uuid] = projectUuid
    import_group[uuid] = importGroupUuid

    if imagePath == None:
        unavailable.add(uuid)
        basename_of[uuid] = None
        extension_of[uuid] = None
        continue

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
        children_of[projectUuid].add(uuid)
    else:
        unavailable.add(uuid)

    if origfname == None and uuid not in unavailable:
        raise Exception("No original file name. REBUILD DATABASE!")

    if origfname == None and uuid in unavailable:
        continue

    #split the file into basename and file extension
    if "." in origfname:
        ext,basename = origfname[::-1].split(".", 1)
        ext,basename = ("." + ext[::-1]),basename[::-1]
        basename_of[uuid] = basename
        extension_of[uuid] = ext
        name_of[uuid] = basename + ext
    else:
        print(origfname)
        raise Exception("No file extention!")


        
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
        hasKeywords, masterHeight, masterWidth in cur.execute(
        'select uuid, name, masterUuid, rawMasterUuid, nonRawMasterUuid, '
        'hasEnabledAdjustments, versionNumber, mainRating, hasKeywords, '
        'masterHeight, masterWidth '
        'from RKVersion'):
    test1 = import_group[master]
    test2 = import_group_path[test1]
    version_file = (import_group_path[import_group[master]] / master /
            ("Version-" + str(versionNum) + ".apversion"))

    caption = None
    title = None
    keywords = None
    previewJpegHeight = None
    previewJpegWidth = None
    if versionNum > 0:
        if not version_file.exists():
            print("Version File does not exist: " + str(version_file))
            continue

        with open(version_file, 'rb') as f:
            try:
                parsed = plistlib.load(f)
                #print(parsed)
            except Exception as e:
                print(version_file)
                raise Exception("File is not (b)plist")

        if "imageProxyState" in parsed:
            upToDate = parsed["imageProxyState"]["fullSizePreviewUpToDate"]
        else:
            raise Exception("No imageProxyState! GENERATE PREVIEWS")
        if adjusted:
            previewPath = (path_to_aplib / "Previews"
                    / parsed["imageProxyState"]["fullSizePreviewPath"])
            previewJpegHeight = parsed["imageProxyState"]["previewJpegHeight"]
            previewJpegWidth = parsed["imageProxyState"]["previewJpegWidth"]
        else:
            previewPath = None #TODO?

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
    basename_of[uuid] = name #version name

    master_of[uuid] = master
    master_set = {nonraw, raw}
    if None in master_set:
        master_set.remove(None)
    all_masters_of[uuid] = master_set

    #if len(master_set) > 1:
        #raise Exception("Broken assumtion: more than one master")

    if hasKeywords == 1:
        if keywords != None:
            addMetadata(uuid, "keywords", keywords)

    if mainRating != 0:
        addMetadata(uuid, "rating", mainRating)

    if caption != None:
        addMetadata(uuid, "caption", caption)

    if title != None:
        addMetadata(uuid, "title", title)

    if name != basename_of[master]:
        version_name_differs = True
        #print("name is different from master")
        #print("master:", basename_of[master])
        #print("version:", name)
    else:
        #print("version name is same as master")
        version_name_differs = False

    if adjusted == 1 and upToDate != True and STRICT_PREVIEW_CHECK == True and master not in unavailable:
        print(basename_of[uuid])
        print(uuid)
        raise Exception("Preview not up to date!")

    if adjusted == 1 and upToDate == True:
        if master not in unavailable:
            if previewJpegHeight * previewJpegWidth * 4 == masterHeight * masterWidth:
                raise Exception("Preview is half size")
        adjusted_photos.add(uuid)
        location_of[uuid] = previewPath
        basename_of[uuid] += " adjusted"
        extension_of[uuid] = ".jpg"
        name_of[uuid] = basename_of[uuid] + extension_of[uuid]
        children_of[parent_of[master]].add(uuid)
    elif master not in unavailable:
        extension_of[uuid] = extension_of[master]
        name_of[uuid] = name + extension_of[uuid]
        location_of[uuid] = location_of[master]

        if version_name_differs or (uuid in metadata):
            if versionNum == 1:
                if version_name_differs:
                    #combine version and original file name
                    if basename_of[master] in name:
                        basename_of[master] = name
                    elif name in basename_of[master]:
                        #version name contained in master
                        #do nothing
                        pass
                    else:
                        basename_of[master] += " -- " + name
                if uuid in metadata:
                    metadata[master] = metadata[uuid]
            else:
                children_of[parent_of[master]].add(uuid)
        else:
            #nothing to export except originals
            pass


vprint("done.")

        

#From table RKAlbum
#holds info on every album in the aplib (some are built in)
vprint("Reading RKAlbum...", end='', flush=True)
for uuid, albumType, subclass, name, parent in cur.execute(
        'select uuid, albumType, albumSubclass, name, folderUuid from RKAlbum'):
    if albumType == 2:
        pass
    elif albumType == 5:
        #LIGHT TABLE
        pass
    elif albumType == 8:
        pass
    #these seem to be the only albums that are important
    elif albumType == 1:
        if subclass == 3 and uuid != "lastImportAlbum":
            type_of[uuid] = type_album
            parent_of[uuid] = parent

            name_of[uuid] = name
            children_of[uuid] = set()
            if parent not in children_of:
                children_of[parent] = set()
            children_of[parent].add(uuid)
            albumFilePath = path_to_aplib / "Database/Albums" / (uuid + ".apalbum")

            try:
                with open(albumFilePath, "rb") as f:
                    #parsed = bplist.parse(f.read())
                    parsed = plistlib.load(f)

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
                        if vuuid in all_masters_of:
                            for master in all_masters_of[vuuid]:
                                if master not in unavailable:
                                    children_of[uuid].add(master)

                        # if the ECLIPSE option is set, 
                        # remove items from the parental project
                        # if they exist there to prevent duplication
                        if ECLIPSE == True and parent_project != None and vuuid in all_masters_of:
                            for item in [vuuid] + list(all_masters_of[vuuid]):
                                try:
                                    children_of[parent_project].remove(item)
                                except KeyError as e:
                                    pass
                        #if photo is adjusted, add it as a child of the album
                        if vuuid in adjusted_photos:
                            children_of[uuid].add(vuuid)
            except RuntimeError as e:
                print("Unable to parse: " + str(albumFilePath) + " ("
                        + name_of[uuid] + ")")
                raise e

    else:
        print(albumType)
        print(name)
        print(uuid)
        raise Exception("Unknown Album Type")

vprint("done.")


################################################
# Pre-Export Sanity Checks
################################################

for uuid in list(children_of.keys()):
    if len(children_of[uuid]) == 0 and type_of[uuid] in [1,2,3]:
        #prune empty directories
        del children_of[uuid]
        children_of[parent_of[uuid]].remove(uuid)

for uuid in children_of.keys():
    if len(children_of[uuid]) > DIRECTORY_THRESHOLD:
        print(name_of[uuid] + ": " + str(len(children_of[uuid])))
        raise Exception("Warning! Items exceed threshold.")

vprint("Passed sanity checks.")

vprint("There are " + str(len(metadata)) + " photos with metadata.")

vprint("There are " + str(len(adjusted_photos)) + " adjusted photos")

if len(adjusted_photos) > 0 and (previewQuality < 9 or previewSizeLimit != 1):
    raise Exception("Adjusted Photos Present but suboptimal preview quality!")

#input("Proceed?")

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
            try:
                os.mkdir(path / name_of[uuid]) #create a directory
            except FileExistsError as e:
                pass

        #sort the children so that directories come first
        for child in sorted(list(children_of[uuid]), key=lambda c: type_of[c]):
            export(child, path / name_of[uuid]) #recurse on each child

    elif type_of[uuid] == type_original or (type_of[uuid] == type_version 
            and EXPORT_ADJUSTED):
        

        #don't overwrite files of the same name
        counter = 0
        basename = basename_of[uuid]
        name_of[uuid] = basename + extension_of[uuid]
        while (path / name_of[uuid]).exists():
            counter += 1
            counter_str = " (" + str(counter) + ")"
            basename_of[uuid] = basename + counter_str
            name_of[uuid] = basename_of[uuid] + extension_of[uuid]


        if uuid in location_of:
            vprint(str(path / name_of[uuid]))
            if DRY_RUN == False:
                copy2(location_of[uuid], path / name_of[uuid])
            else:
                test1 = location_of[uuid]
                test2 = name_of[uuid]
            if uuid in metadata:
                vprint(path / (basename_of[uuid] + ".xmp"))
                vprint(metadata[uuid])
                if DRY_RUN == False:
                    writeMetadataXMP(uuid, path / (basename_of[uuid] + ".xmp"))
                else:
                    test1 = basename_of[uuid]

#Exclude some junk
exclude_if_empty = ['TopLevelBooks', 'TopLevelAlbums', 'TopLevelKeepsakes', 'TopLevelSlideshows',
        'TopLevelWebProjects', 'TopLevelLightTables', 'PublishedProjects', 'TrashFolder']
for uuid in exclude_if_empty:
    if uuid in children_of and len(children_of[uuid]) == 0:
        children_of[parent_of[uuid]].remove(uuid)

root_uuid = "LibraryFolder"
name_of["LibraryFolder"] = (path_to_aplib.name + " xptd " 
        + str(datetime.now().__format__("%Y%m%d%H%M%S")))
name_of["TopLevelAlbums"] = "Albums"
export(root_uuid, export_path)

