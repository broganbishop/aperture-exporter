import os
import sys
import re
import plistlib
import sqlite3
import settings
from pathlib import Path
from shutil import copy2
from datetime import datetime
from utils import getSHA256
from utils import AlreadyExportedException

def vprint(*args, **kwargs):
    if settings.options["VERBOSE"]:
        print(*args, **kwargs)

class Aplib():
    def __init__(self, path_to_aplib, export_path):
        self.path_to_aplib = path_to_aplib
        self.export_path = export_path

        # uuid -- type of object
        self.type_of = {}
        self.type_folder = 1
        self.type_project = 2
        self.type_album = 3
        self.type_original = 4
        self.type_version = 5
        #
        #uuid (parent) -- list of uuids (children)
        self.children_of = {}
        #
        #uuid -- name of thing (string)
        self.name_of = {}
        self.original_file_name_of = {}
        self.version_name_of = {}
        self.basename_of = {}
        self.extension_of = {}
        #
        #uuid (child) -- uuid (parent)
        self.parent_of = {}
        #
        #uuid --> path of object
        #version --> full size preview
        #master --> original photo
        self.location_of = {}
        #
        # uuid (version) --> uuid(s) of originals (set)
        # todo: better as a tuple?
        self.all_masters_of = {}
        #
        # uuid (version) --> master uuid
        self.master_of = {}
        #
        #list of uuids (versions that have adjustments)
        self.adjusted_photos = set()
        #
        #import group uuid --> path (to version info)
        self.import_group_path = {}
        #
        #master uuid --> import group uuid
        self.import_group = {}
        #
        self.unavailable = set()
        #
        self.sha256_of = {}
        #
        self.volume = {}
        #
        self.metadata = {}


        self.checkAplibExists()
        self.checkExportDoesNotExist()
        self.readInfoPlist()

        self.connectToAPDB()
        self.readRKAdminData()
        self.readRKFolder()
        self.readRKImportGroup()
        self.readRKVolume()
        self.readRKMaster()
        self.readRKVersion()
        self.readRKAlbum()


    def checkAplibExists(self):
        if not self.path_to_aplib.exists():
            raise Exception("Aplibrary does not exist")

    def checkExportDoesNotExist(self):
        pattern = re.compile("^.*\.aplibrary xptd [0-9]*$")
        already_exported = False
        for _,dirs,_ in os.walk(self.export_path):
            for d in dirs:
                if pattern.fullmatch(d) != None:
                    raise AlreadyExportedException()
            break

    def readInfoPlist(self):
        with open(self.path_to_aplib / "Info.plist", "rb") as info_plist:
            info = plistlib.load(info_plist)
            #check version
            if info["CFBundleShortVersionString"] != "3.6":
                raise Exception("Aperture Library is not version 3.6")

    def connectToAPDB(self):
        self.apdb = sqlite3.connect(self.path_to_aplib / "Database/apdb/Library.apdb").cursor()

    def readRKAdminData(self):
        #general info about library
        vprint("Reading RKAdminData...", flush=True)
        for area, name, value in self.apdb.execute(
                'select propertyArea, propertyName, propertyValue from RKAdminData'):
            if area == "database":
                if name == "databaseUuid":
                    vprint("database uuid = ", value)
                    self.uuid = value
                elif name == "previewSizeLimit":
                    value = int(value)
                    vprint("previewSizeLimit =", value)
                    self.previewSizeLimit = value
                elif name == "previewQuality":
                    value = round(float(value) * 12)
                    vprint("previewQuality =", value)
                    self.previewQuality = value
        vprint("done.")


    def readRKFolder(self):
        #From table RKFolder
        #This table holds information about all folders and projects
        vprint("Reading RKFolder...", end="", flush=True)
        for uuid, parent, name, folderType in self.apdb.execute(
                'select uuid, parentFolderUuid, name, folderType from RKFolder'):
            if uuid not in self.children_of:
                self.children_of[uuid] = set()
            if parent not in self.children_of:
                self.children_of[parent] = set()
            self.children_of[parent].add(uuid)
            if "/" in name:
                #TODO: problems with name mashing
                name = name.replace("/", "-")
            if ":" in name:
                name = name.replace(":", "-")
            self.name_of[uuid] = name
            self.parent_of[uuid] = parent

            if folderType == 1:
                self.type_of[uuid] = self.type_folder
            elif folderType == 2:
                self.type_of[uuid] = self.type_project
            elif folderType == 3: #Same as 1?
                self.type_of[uuid] = self.type_folder
            else:
                raise Exception("Item in RKFolder has undefined type!")
        vprint("done.")


    def readRKImportGroup(self):
        # RKImportGroup
        # Date and time of each import group
        # (used to store versions/full sized previews)
        vprint("Reading RKImportGroup...", end="", flush=True)
        for uuid, year, month, day, time in self.apdb.execute(
                'select uuid, importYear, importMonth, importDay, importTime from RKImportGroup'):
            self.import_group_path[uuid] = (self.path_to_aplib / "Database" / "Versions"
                    / year / month / day / (year + month + day + "-" + time))
        vprint("done.")

    def readRKVolume(self):
        #RKVolume
        #volume info for referenced files
        vprint("Reading RKVolume...", end='', flush=True)
        for uuid, name in self.apdb.execute('select uuid, name from RKVolume'):
            self.volume[uuid] = name
        vprint("done.")



    def readRKMaster(self):
        #RKMaster
        #add originals to dicts and a list
        vprint("Reading RKMaster...", end='', flush=True)
        for uuid, origfname, imagePath, projectUuid, importGroupUuid, isMissing, \
                isRef, vol_uuid, origvname, inTrash in self.apdb.execute(
                'select uuid, originalFileName, imagePath, projectUuid, importGroupUuid, isMissing, '
                'fileIsReference, fileVolumeUuid, originalVersionName, isInTrash from RKMaster'):
            self.type_of[uuid] = self.type_original
            if inTrash == 1:
                projectUuid = "TrashFolder"
            self.parent_of[uuid] = projectUuid
            self.import_group[uuid] = importGroupUuid

            if imagePath == None:
                self.unavailable.add(uuid)
                self.basename_of[uuid] = None
                self.extension_of[uuid] = None
                continue

            if isRef == 0:
                fullImagePath = self.path_to_aplib / "Masters" / imagePath
            elif isRef == 1:
                if vol_uuid in self.volume:
                    fullImagePath = Path("/Volumes") / self.volume[vol_uuid] / imagePath 
                else:
                    #TODO:Why would vol_uuid not be in self.volume?
                    #is this the proper action?
                    fullImagePath = None

            #If the file is present, then add it to be exported
            if fullImagePath != None and fullImagePath.exists() and fullImagePath.is_file():
                if isMissing == 1:
                    raise Exception("File 'Missing' but exists!")
                #sha256_of[uuid] = getSHA256(fullImagePath)
                #truncated_hash = ("{sha256+" + sha256_of[uuid][:8] + "}")[::-1]
                self.location_of[uuid] = fullImagePath
                self.children_of[projectUuid].add(uuid)
            else:
                self.unavailable.add(uuid)

            if origfname == None and uuid not in self.unavailable:
                raise Exception("No original file name. REBUILD DATABASE!")

            if origfname == None and uuid in self.unavailable:
                self.basename_of[uuid] = None
                self.extension_of[uuid] = None
                continue

            #split the file into basename and file extension
            if "." in origfname:
                ext,basename = origfname[::-1].split(".", 1)
                ext,basename = ("." + ext[::-1]),basename[::-1]
                self.basename_of[uuid] = basename
                self.extension_of[uuid] = ext
                self.name_of[uuid] = basename + ext
            else:
                print(origfname)
                raise Exception("No file extention!")


                
        vprint("done.")


    def addMetadata(self, uuid, key, data):
        if uuid not in self.metadata:
            self.metadata[uuid] = {}

        if key == "keywords":
            if "keywords" not in self.metadata[uuid]:
                self.metadata[uuid]["keywords"] = set()
            self.metadata[uuid]["keywords"] |= set(map(str.strip, data))

        elif key == "rating":
            if "rating" not in self.metadata[uuid]:
                self.metadata[uuid]["rating"] = data
            else:
                raise Exception("Multiple Ratings")
                self.metadata[uuid]["rating"] = max(self.metadata[uuid]["rating"], data)

        else:
            if key in self.metadata[uuid]:
                print(uuid, key, data)
                raise Exception("Key already in metadata")
            else:
                self.metadata[uuid][key] = data

            


    def readRKVersion(self):
        #From table RKVersion
        #information about versions (uuid of corresponding originals)
        vprint("Reading RKVersion...", end='', flush=True)
        for uuid, name, master, raw, nonraw, adjusted, versionNum, mainRating,\
                hasKeywords, masterHeight, masterWidth in self.apdb.execute(
                'select uuid, name, masterUuid, rawMasterUuid, nonRawMasterUuid, '
                'hasEnabledAdjustments, versionNumber, mainRating, hasKeywords, '
                'masterHeight, masterWidth '
                'from RKVersion'):
            test1 = self.import_group[master]
            test2 = self.import_group_path[test1]
            version_file = (self.import_group_path[self.import_group[master]] / master /
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
                    previewPath = (self.path_to_aplib / "Previews"
                            / parsed["imageProxyState"]["fullSizePreviewPath"])
                    if not previewPath.exists():
                        if master not in self.unavailable:
                            raise Exception("preview does not exist at recorded path")
                        else:
                            #TODO: correct action?
                            pass

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

            self.type_of[uuid] = self.type_version
            self.basename_of[uuid] = name #version name

            self.master_of[uuid] = master
            master_set = {nonraw, raw}
            if None in master_set:
                master_set.remove(None)
            self.all_masters_of[uuid] = master_set

            #if len(master_set) > 1:
                #raise Exception("Broken assumtion: more than one master")

            if hasKeywords == 1:
                if keywords != None:
                    self.addMetadata(uuid, "keywords", keywords)

            if mainRating != 0:
                self.addMetadata(uuid, "rating", mainRating)

            if caption != None:
                self.addMetadata(uuid, "caption", caption)

            if title != None:
                self.addMetadata(uuid, "title", title)

            if name != self.basename_of[master]:
                version_name_differs = True
                #print("name is different from master")
                #print("master:", basename_of[master])
                #print("version:", name)
            else:
                #print("version name is same as master")
                version_name_differs = False

            if adjusted == 1 and upToDate != True and settings.options["STRICT_PREVIEW_CHECK"] and master not in self.unavailable:
                print(self.basename_of[uuid])
                print(uuid)
                raise Exception("Preview not up to date!")

            if adjusted == 1 and upToDate == True:
                if master not in self.unavailable:
                    if previewJpegHeight * previewJpegWidth * 4 == masterHeight * masterWidth:
                        raise Exception("Preview is half size")
                self.adjusted_photos.add(uuid)
                self.location_of[uuid] = previewPath
                self.basename_of[uuid] += " adjusted"
                self.extension_of[uuid] = ".jpg"
                self.name_of[uuid] = self.basename_of[uuid] + self.extension_of[uuid]
                self.children_of[self.parent_of[master]].add(uuid)
            elif master not in self.unavailable:
                self.extension_of[uuid] = self.extension_of[master]
                self.name_of[uuid] = name + self.extension_of[uuid]
                self.location_of[uuid] = self.location_of[master]

                if version_name_differs or (uuid in self.metadata):
                    if versionNum == 1:
                        if version_name_differs:
                            #combine version and original file name
                            if self.basename_of[master] in name:
                                self.basename_of[master] = name
                            elif name in self.basename_of[master]:
                                #version name contained in master
                                #do nothing
                                pass
                            else:
                                self.basename_of[master] += " -- " + name
                        if uuid in self.metadata:
                            self.metadata[master] = self.metadata[uuid]
                    else:
                        self.children_of[self.parent_of[master]].add(uuid)
                else:
                    #nothing to export except originals
                    pass


        vprint("done.")

                
    def readRKAlbum(self):
        #From table RKAlbum
        #holds info on every album in the aplib (some are built in)
        vprint("Reading RKAlbum...", end='', flush=True)
        for uuid, albumType, subclass, name, parent in self.apdb.execute(
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
                    self.type_of[uuid] = self.type_album
                    self.parent_of[uuid] = parent

                    self.name_of[uuid] = name
                    self.children_of[uuid] = set()
                    if parent not in self.children_of:
                        self.children_of[parent] = set()
                    self.children_of[parent].add(uuid)
                    albumFilePath = self.path_to_aplib / "Database/Albums" / (uuid + ".apalbum")

                    try:
                        with open(albumFilePath, "rb") as f:
                            #parsed = bplist.parse(f.read())
                            parsed = plistlib.load(f)

                            #determine parent project if any
                            parent_project = None
                            if settings.options["ECLIPSE"]:
                                current_uuid = uuid
                                while self.type_of[current_uuid] != self.type_project:
                                    current_uuid = self.parent_of[current_uuid]
                                    if current_uuid not in self.type_of:
                                        break
                                    elif self.type_of[current_uuid] == self.type_project:
                                        parent_project = current_uuid
                                        break
                                    elif current_uuid == "AllProjectsItem":
                                        break

                            #add the masters as children of the album
                            for vuuid in parsed["versionUuids"]:
                                if vuuid in self.all_masters_of:
                                    for master in self.all_masters_of[vuuid]:
                                        if master not in self.unavailable:
                                            self.children_of[uuid].add(master)

                                # if the ECLIPSE option is set, 
                                # remove items from the parental project
                                # if they exist there to prevent duplication
                                if settings.options["ECLIPSE"] and parent_project != None and vuuid in self.all_masters_of:
                                    for item in [vuuid] + list(self.all_masters_of[vuuid]):
                                        try:
                                            self.children_of[parent_project].remove(item)
                                        except KeyError as e:
                                            pass
                                #if photo is adjusted, add it as a child of the album
                                if vuuid in self.adjusted_photos:
                                    self.children_of[uuid].add(vuuid)
                    except RuntimeError as e:
                        print("Unable to parse: " + str(albumFilePath) + " ("
                                + self.name_of[uuid] + ")")
                        raise e

            else:
                print(albumType)
                print(name)
                print(uuid)
                raise Exception("Unknown Album Type")

        vprint("done.")

    def writeMetadataXMP(self, uuid, path):
        if uuid not in self.metadata:
            raise Exception("No metadata to write!")
            return

        if "rating" in self.metadata[uuid]:
            rating_string = f"\t<xap:Rating>{self.metadata[uuid]['rating']}</xap:Rating>\n"
        else:
            rating_string = ""

        if "keywords" in self.metadata[uuid]:
            keyword_string = "\t<dc:subject><rdf:Bag>\n"
            for k in self.metadata[uuid]["keywords"]:
                keyword_string += f"\t\t<rdf:li>{k}</rdf:li>\n"
            keyword_string += "\t</rdf:Bag></dc:subject>\n"
        else:
            keyword_string = ""

        if "caption" in self.metadata[uuid]:
            caption_string = "\t<dc:description><rdf:Alt><rdf:li xml:lang='x-default'>"
            caption_string += self.metadata[uuid]["caption"]
            caption_string += "</rdf:li></rdf:Alt></dc:description>\n"
        else:
            caption_string = ""

        if "title" in self.metadata[uuid]:
            title_string = "\t<dc:title><rdf:Alt><rdf:li xml:lang='x-default'>"
            title_string += self.metadata[uuid]["title"]
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


    def preExportSanityChecks(self):

        for uuid in list(self.children_of.keys()):
            if len(self.children_of[uuid]) == 0 and self.type_of[uuid] in [1,2,3]:
                #prune empty directories
                del self.children_of[uuid]
                self.children_of[self.parent_of[uuid]].remove(uuid)

        for uuid in self.children_of.keys():
            if len(self.children_of[uuid]) > settings.options["DIRECTORY_THRESHOLD"]:
                print(self.name_of[uuid] + ": " + str(len(self.children_of[uuid])))
                raise Exception("Warning! Items exceed threshold.")

        vprint("Passed sanity checks.")

        vprint("There are " + str(len(self.metadata)) + " photos with metadata.")

        vprint("There are " + str(len(self.adjusted_photos)) + " adjusted photos")

        if len(self.adjusted_photos) > 0 and (self.previewQuality < 9 or self.previewSizeLimit != 1):
            raise Exception("Adjusted Photos Present but suboptimal preview quality!")


    def export(self):
        self.preExportSanityChecks()

        #Exclude some junk
        exclude_if_empty = ['TopLevelBooks', 'TopLevelAlbums', 'TopLevelKeepsakes', 'TopLevelSlideshows',
                'TopLevelWebProjects', 'TopLevelLightTables', 'PublishedProjects', 'TrashFolder']
        for uuid in exclude_if_empty:
            if uuid in self.children_of and len(self.children_of[uuid]) == 0:
                self.children_of[self.parent_of[uuid]].remove(uuid)

        root_uuid = "LibraryFolder"
        self.name_of["LibraryFolder"] = (self.path_to_aplib.name + " xptd " 
                + str(datetime.now().__format__("%Y%m%d%H%M%S")))
        self.name_of["TopLevelAlbums"] = "Albums"


        self.checkExportDoesNotExist()#a second time?

        #create temporary file
        tmp_file = Path(self.export_path) / (self.name_of[root_uuid] + ".inprogress")
        with open(tmp_file, "w") as f:
            f.write("")

        try:
            #Do the export
            self.recursiveExport(root_uuid, self.export_path)
            #delete temporary file when finished
            os.remove(tmp_file)

        except Exception as e:
            print("Exception!")
            print(self.path_to_aplib)
            print(e)

        

        

    def recursiveExport(self, uuid, path):

        if settings.options["EXPORT_ALBUMS"] == False:
            if self.type_of[uuid] == self.type_album:
                return

        if self.type_of[uuid] in [self.type_folder, self.type_project, self.type_album]:
            #skip empty directories
            #if uuid not in children_of or len(children_of[uuid]) == 0:
                #return
            vprint(str(path / self.name_of[uuid]))
            if settings.options["DRY_RUN"] == False:
                try:
                    os.mkdir(path / self.name_of[uuid]) #create a directory
                except FileExistsError as e:
                    pass

            #sort the children so that directories come first
            for child in sorted(list(self.children_of[uuid]), key=lambda c: self.type_of[c]):
                self.recursiveExport(child, path / self.name_of[uuid]) #recurse on each child

        elif self.type_of[uuid] == self.type_original or (self.type_of[uuid] == self.type_version 
                and settings.options["EXPORT_ADJUSTED"]):
            

            #don't overwrite files of the same name
            counter = 0
            basename = self.basename_of[uuid]
            self.name_of[uuid] = basename + self.extension_of[uuid]
            counter_str = ""
            while ((path / self.name_of[uuid]).exists() or 
                    (path / (self.basename_of[uuid] + counter_str + ".xmp")).exists()):
                counter += 1
                counter_str = " (" + str(counter) + ")"
                self.basename_of[uuid] = basename + counter_str
                self.name_of[uuid] = self.basename_of[uuid] + self.extension_of[uuid]


            if uuid in self.location_of:
                vprint(str(path / self.name_of[uuid]))
                if settings.options["DRY_RUN"] == False:
                    copy2(self.location_of[uuid], path / self.name_of[uuid])
                else:
                    test1 = self.location_of[uuid]
                    test2 = self.name_of[uuid]
                if uuid in self.metadata:
                    vprint(path / (self.basename_of[uuid] + ".xmp"))
                    vprint(self.metadata[uuid])
                    if settings.options["DRY_RUN"] == False:
                        self.writeMetadataXMP(uuid, path / (self.basename_of[uuid] + ".xmp"))
                    else:
                        test1 = self.basename_of[uuid]

    
    

class Master():
    pass

class Version():
    pass

class Folder():
    pass

class Album():
    pass

class Project():
    pass
