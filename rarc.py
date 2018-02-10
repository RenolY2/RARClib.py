from struct import pack, unpack
from io import BytesIO

from yaz0 import decompress, compress_fast, read_uint32, read_uint16


def stringtable_get_name(f, stringtable_offset, offset):
    current = f.tell()
    f.seek(stringtable_offset+offset)

    stringlen = 0
    while f.read(1) != b"\x00":
        stringlen += 1

    f.seek(stringtable_offset+offset)

    filename = f.read(stringlen)
    try:
        decodedfilename = filename.decode("shift-jis")
    except:
        print("filename", filename)
        print("failed")
        raise
    f.seek(current)

    return decodedfilename

def split_path(path): # Splits path at first backslash encountered
    for i, char in enumerate(path):
        if char == "/" or char == "\\":
            if len(path) == i+1:
                return path[:i], None
            else:
                return path[:i], path[i+1:]

    return path, None

class Directory(object):
    def __init__(self, dirname, nodeindex=None):
        self.files = {}
        self.subdirs = {}
        self.name = dirname
        self._nodeindex = nodeindex

        self.parent = None

    @classmethod
    def from_dir(cls, path, follow_symlinks=False):
        dirname = os.path.basename(path)

        dir = cls(dirname)

        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=follow_symlinks):
                    dir = Directory.from_dir(entry.path, follow_symlinks=follow_symlinks)
                    dir.subdirs[entry.name] = dir

                elif entry.is_file(follow_symlinks=follow_symlinks):
                    with open(entry.path, "rb") as f:
                        file = File.from_file(entry.name, f)
                    dir.files[entry.name] = file

        return dir



    @classmethod
    def from_node(cls, f, _name, stringtable_offset, globalentryoffset, dataoffset, nodelist, currentnodeindex, parents=None):
        print("=============================")
        print("Creating new node with index", currentnodeindex)
        name, unknown, entrycount, entryoffset = nodelist[currentnodeindex]

        newdir = cls(name, currentnodeindex)

        firstentry = globalentryoffset+entryoffset
        print("Node", currentnodeindex, name, entrycount, entryoffset)
        print("offset", f.tell())
        for i in range(entrycount):
            offset = globalentryoffset + (entryoffset+i)*20
            f.seek(offset)

            fileentry_data = f.read(20)

            fileid, hashcode, flags, padbyte, nameoffset, filedataoffset, datasize, padding = unpack(">HHBBHIII", fileentry_data)
            print("offset", hex(firstentry+i*20), fileid, flags, nameoffset)

            name = stringtable_get_name(f, stringtable_offset, nameoffset)

            print("name", name)

            if name == "." or name == ".." or name == "":
                continue
            #print(name, nameoffset)

            if (flags & 0b10) != 0 and not (flags & 0b1) == 1: #fileid == 0xFFFF: # entry is a sub directory
                #fileentrydata = f.read(12)
                #nodeindex, datasize, padding = unpack(">III", fileentrydata)
                nodeindex = filedataoffset

                name = stringtable_get_name(f, stringtable_offset, nameoffset)


                newparents = [currentnodeindex]
                if parents is not None:
                    newparents.extend(parents)

                if nodeindex in newparents:
                    print("Detected recursive directory: ", name)

                    print("Skipping")
                    continue

                subdir = Directory.from_node(f, name, stringtable_offset, globalentryoffset, dataoffset, nodelist, nodeindex, parents=newparents)
                subdir.parent = newdir

                newdir.subdirs[subdir.name] = subdir


            else: # entry is a file
                f.seek(offset)
                file = File.from_fileentry(f, stringtable_offset, dataoffset, fileid, hashcode, flags, nameoffset, filedataoffset, datasize)
                newdir.files[file.name] = file

        return newdir

    def walk(self, _path=None):
        if _path is None:
            dirpath = self.name
        else:
            dirpath = _path+"/"+self.name

        #print("Yielding", dirpath)

        yield (dirpath, self.subdirs.keys(), self.files.keys())

        for dirname, dir in self.subdirs.items():
            #print("yielding subdir", dirname)
            yield from dir.walk(dirpath)

    def __getitem__(self, path):
        name, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if name in self.subdirs:
                return self.subdirs[name]
            elif name in self.files:
                return self.files[name]
            else:
                raise FileNotFoundError(path)
        elif name in self.files:
            raise RuntimeError("File", name, "is a directory in path", path, "which should not happen!")
        else:
            return self.subdirs[name][rest]

    def __setitem__(self, path, entry):
        name, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if isinstance(name, File):
                if name in self.subdirs:
                    raise FileExistsError("Cannot add file, '{}' already exists as a directory".format(path))

                self.files[name] = entry
            elif isinstance(name, Directory):
                if name in self.files:
                    raise FileExistsError("Cannot add directory, '{}' already exists as a file".format(path))

                self.subdirs[name] = entry
            else:
                raise TypeError("Entry should be of type File or Directory but is type {}".format(type(entry)))

        elif name in self.files:
            raise RuntimeError("File", name, "is a directory in path", path, "which should not happen!")
        else:
            return self.subdirs[name][rest]

    def listdir(self, path):
        if path == ".":
            dir = self
        else:
            dir = self[path]

        entries = []
        entries.extend(dir.files.keys())
        entries.extend(dir.subdirs.keys())
        return entries

    def extract_to(self, path):
        current_dirpath = os.path.join(path, self.name)
        os.makedirs(current_dirpath, exist_ok=True)

        for filename, file in self.files.items():
            filepath = os.path.join(current_dirpath, filename)
            with open(filepath, "wb") as f:
                file.dump(f)

        for dirname, dir in self.subdirs.items():
            dir.extract_to(current_dirpath)

class File(BytesIO):
    def __init__(self, filename, fileid=None, hashcode=None, flags=None):
        super().__init__()

        self.name = filename
        self._fileid = fileid
        self._hashcode = hashcode
        self._flags = flags

    @classmethod
    def from_file(cls, filename, f):
        file = cls(filename)

        file.write(f.read())
        file.seek(0)

        return file



    @classmethod
    def from_fileentry(cls, f, stringtable_offset, globaldataoffset, fileid, hashcode, flags, nameoffset, filedataoffset, datasize):
        filename = stringtable_get_name(f, stringtable_offset, nameoffset)
        """print("-----")
        print("File", len(filename))
        print("size", datasize)
        print(hex(stringtable_offset), hex(nameoffset))
        print(hex(datasize))"""
        file = cls(filename, fileid, hashcode, flags)

        f.seek(globaldataoffset+filedataoffset)
        file.write(f.read(datasize))

        # Reset file position
        file.seek(0)

        return file

    def dump(self, f):
        f.write(self.getvalue())


class Archive(object):
    def __init__(self):
        self.root = None

    @classmethod
    def from_dir(cls, path, follow_symlinks):
        arc = cls()
        dir = Directory.from_dir(path, follow_symlinks=follow_symlinks)
        arc.root = dir

        return arc


    @classmethod
    def from_file(cls, f):
        newarc = cls()

        header = f.read(4)
        size = read_uint32(f)
        f.read(4) #unknown

        data_offset = read_uint32(f) + 0x20
        f.read(16) # Unknown
        node_count = read_uint32(f)
        f.read(8) # Unknown
        file_entry_offset = read_uint32(f) + 0x20
        f.read(4) # Unknown
        stringtable_offset = read_uint32(f) + 0x20
        f.read(8) # Unknown
        print("nodes start at", hex(f.tell()))
        nodes = []

        print("Archive has", node_count, "nodes")
        print("data offset", hex(data_offset))
        for i in range(node_count):
            nodetype = f.read(4)
            nodedata = f.read(4+2+2+4)
            nameoffset, unknown, entrycount, entryoffset = unpack(">IHHI", nodedata)

            dir_name = stringtable_get_name(f, stringtable_offset, nameoffset)

            print(dir_name, hex(stringtable_offset), hex(nameoffset))
            nodes.append((dir_name, unknown, entrycount, entryoffset))
        rootfoldername = nodes[0][0]
        newarc.root = Directory.from_node(f, rootfoldername, stringtable_offset, file_entry_offset, data_offset, nodes, 0)

        return newarc


    def listdir(self, path):
        if path == ".":
            return [self.root.name]
        else:
            dir = self[path]
            entries = []
            entries.extend(dir.files.keys())
            entries.extend(dir.subdirs.keys())
            return entries

    def __getitem__(self, path):
        dirname, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if dirname != self.root.name:
                raise FileNotFoundError(path)
            else:
                return self.root
        else:
            return self.root[rest]

    def __setitem__(self, path, entry):
        dirname, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if dirname != self.root.name:
                raise RuntimeError("Cannot have more than one directory in the root.")
            elif isinstance(entry, Directory):
                self.root = entry
            else:
                raise TypeError("Root entry should be of type directory but is type '{}'".format(type(entry)))
        else:
            self.root[rest] = entry

    def extract_to(self, path):
        self.root.extract_to(path)


if __name__ == "__main__":
    import os
    with open("airport0.szs 0.rarc", "rb") as f:
        myarc = Archive.from_file(f)

    print(myarc.root.name)
    print("done reading")

    print(myarc["scene"])
    print(myarc.listdir("scene"))
    print(myarc.listdir("scene/kinojii"))


    myarc.extract_to("arctest")


