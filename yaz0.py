

## Implementation of a yaz0 decoder/encoder in Python, by Yoshi2
## Using the specifications in http://www.amnoid.de/gc/yaz0.txt

from struct import unpack, pack
import os
import re
import hashlib
import math

from timeit import default_timer as time
from io import BytesIO
#from cStringIO import StringIO

#class yaz0():
#    def __init__(self, inputobj, outputobj = None, compress = False):

def read_uint32(f):
    return unpack(">I", f.read(4))[0]
    
def read_uint16(f):
    return unpack(">H", f.read(2))[0]
    
def read_uint8(f):
    return unpack(">B", f.read(1))[0]

def write_limited(f, data, limit):
    if f.tell() >= limit:
        pass
    else:
        f.write(data)
    
def decompress(f, out):
    #if out is None:
    #    out = BytesIO()
    
    # A way to discover the total size of the input data that
    # should be compatible with most file-like objects.
    f.seek(0, 2)
    maxsize = f.tell()
    f.seek(0)
    
    
    header = f.read(4)
    if header != b"Yaz0":
        raise RuntimeError("File is not Yaz0-compressed! Header: {0}".format(header))
    
    decompressed_size = read_uint32(f)
    f.read(8) # padding
    
    """else:
        self.output.write("Yaz0")
        
        self.output.write(struct.pack(">I", self.maxsize))
        self.output.write(chr(0x00)*8)"""
        
    eof = False
    while out.tell() < decompressed_size and not eof:
        code_byte = read_uint8(f)
        
        for i in range(8):
            is_set = ((code_byte << i) & 0x80) != 0 
            
            if is_set:
                out.write(f.read(1)) # Write next byte as-is without requiring decompression
            else:
                if f.tell() >= maxsize-1:
                    eof = True
                    break
                    
                infobyte = read_uint16(f)
                
                bytecount = infobyte >> 12 
                
                if bytecount == 0:
                    bytecount = read_uint8(f) + 0x12 
                else:
                    bytecount += 2
                
                offset = infobyte & 0x0FFF
                
                current = out.tell()
                seekback = current - (offset+1)
                
                if seekback < 0:
                    raise RuntimeError("Malformed Yaz0 file: Seek back position goes below 0")
                    
                out.seek(seekback)
                copy = out.read(bytecount)
                out.seek(current)
                
                write_limited(out, copy, decompressed_size)
                
                
                if len(copy) < bytecount: 
                    # Copy source and copy distance overlap which essentially means that
                    # we have to repeat the copied source to make up for the difference
                    j = 0
                    for i in range(bytecount-len(copy)):
                        write_limited(out, copy[j:j+1], decompressed_size)
                        j = (j+1) % len(copy)
                
    
    if out.tell() > decompressed_size:
        print(  "Warning: output is longer than decompressed size for some reason: "
                "{}/decompressed: {}".format(out.tell(), decompressed_size))

def compress_fast(f, out):
    data = f.read()
    
    maxsize = len(data)
    
    out.write(b"Yaz0")
    out.write(pack(">I", maxsize))
    out.write(b"\x00"*8)
    
    for i in range(maxsize//8):
        start = i*8 
        end = (i+1)*8
        
        if end > maxsize:
            # Pad data with 0's up to 8 bytes
            tocopy = data[start:maxsize] + b"\x00"*(end-maxsize)
        else:
            tocopy = data[start:end]
        
        out.write(b"\xFF") # Set all bits in the code byte to 1 to mark the following 8 bytes as copy 
        out.write(tocopy)

def compress(f, out, compresslevel=9):
    pass
    
    
"""if False:
    # To do: 
    # 1) Optimization
    # 2) Better compression
    # 3) Testing under real conditions 
    #    (e.g. replace a file in a game with a file compressed with this method)
    def compress(self, compressLevel = 0, advanced = False):
        if not self.compressFlag:
            raise RuntimeError("Trying to compress, but compress flag is not set."
                               "Create yaz0 object with compress = True as one of its arguments.")
        
        if compressLevel >= 10 or compressLevel < 0:
            raise RuntimeError("CompressionLevel is limited to 0-9.")
        
        fileobj = self.fileobj
        output = self.output
        maxsize = self.maxsize
        
        # compressLevel can be one of the values from 0 to 9.
        # It will reduce the area in which the method will look
        # for matches and speed up compression slightly.
        compressRatio = (1/10.0) * (compressLevel+1)
        maxSearch = 2**12 - 1
        adjustedSearch = int(maxSearch*compressRatio)
        adjustedMaxBytes = int(math.ceil(15*compressRatio+2))
        
        # The advanced flag will allow the use of a third byte,
        # enabling the method to look for matches that are up to 
        # 256 bytes long. NOT IMPLEMENTED YET
        
        if advanced == False:
            while fileobj.tell() < maxsize:
                buffer = StringIO()
                codeByte = 0
                
                # Compressing data near the end can be troublesome, so we will just read the data
                # and write it uncompressed. Alternatively, checks can be added to
                # the code further down, but that requires more work and testing.
                #if maxsize - fileobj.tell() <= 17*8:
                #    print "Left: {0} bytes".format(maxsize - fileobj.tell())
                #    leftover = fileobj.read(8).ljust(8,chr(0x00))
                #    codeByte = 0xFF
                #    buffer.write(leftover) 
                    
                    
                #else:
                for i in range(8):
                    # 15 bytes can be stored in a nibble. The decompressor will
                    # read 15+2 bytes, possibly to account for the way compression works.
                    maxBytes = adjustedMaxBytes
                    
                    # Store the current file pointer for reference.
                    currentPos = fileobj.tell()
                    
                    # Adjust maxBytes if we are close to the end.
                    if maxsize - currentPos < maxBytes:
                        maxBytes = maxsize - currentPos
                        print "Maxbytes adjusted to", maxBytes
                    
                    # Calculate the starting position for the search
                    searchPos = currentPos-adjustedSearch
                    
                    # Should the starting position be negative, it will be set to 0.
                    # We will also adjust how much we need to read.
                    if searchPos < 0:
                        searchPos = 0
                        realSearch = currentPos
                    else:
                        realSearch = adjustedSearch
                    
                    # toSearch will be the string (up to 2**12 long) in which
                    # we will search for matches of the pattern.
                    pattern = fileobj.read(maxBytes)
                    fileobj.seek(searchPos)
                    toSearch = fileobj.read(realSearch)
                    fileobj.seek(currentPos + len(pattern))
                    
                    index = toSearch.rfind(pattern)
                    
                    # If a match hasn't been found, we will start a loop in which we
                    # will steadily reduce the length of the pattern, increasing the chance
                    # of finding a matching string. The pattern needs to be at least 3 bytes
                    # long, otherwise there is no point in trying to compress it.
                    # (The algorithm uses at least 2 bytes to represent such patterns)
                    while index == -1 and maxBytes > 3:
                        fileobj.seek(currentPos)
                        
                        maxBytes -= 1
                        pattern = fileobj.read(maxBytes)
                        
                        if len(pattern) < maxBytes:
                            maxBytes = len(pattern) 
                            print "adjusted pattern length"
                            
                        index = toSearch.rfind(pattern)
                    
                    if index == -1 or maxBytes <= 2:
                        # No match found. Read a byte and append it to the buffer directly.
                        fileobj.seek(currentPos)
                        byte = fileobj.read(1)
                        
                        # At the end of the file, read() will return an empty string.
                        # In that case we will set the byte to the 0 character.
                        # Hopefully, a decompressor will check the uncompressed size
                        # of the file and remove any padding bytes past this position.
                        if len(byte) == 0:
                            #print "Adding padding"
                            byte = chr(0x00)
                        
                        buffer.write(byte)
                        
                        # Mark the bit in the codebyte as 1.
                        codeByte = (1 << (7-i)) | codeByte
                        
                    else:
                        # A match has been found, we need to calculate its index relative to
                        # the current position. (RealSearch stores the total size of the search string,
                        # while the index variable holds the position of the pattern in the search string)
                        relativeIndex = realSearch - index 
                        
                        # Create the two descriptor bytes which hold the length of the pattern and
                        # its index relative to the current position.
                        # Marking the bit in the codebyte as 0 isn't necessary, it will be 0 by default.
                        byte1, byte2 = self.__build_byte__(maxBytes-2, relativeIndex-1)
                        
                        buffer.write(chr(byte1))
                        buffer.write(chr(byte2))
            
                # Now that everything is done, we will append the code byte and
                # our compressed data from the buffer to the output.
                output.write(chr(codeByte))
                output.write(buffer.getvalue())
        else:
            raise RuntimeError("Advanced compression not implemented yet.")
        
        return output
                    
    def __build_byte__(self, byteCount, position):
        if position >= 2**12:
            raise RuntimeError("{0} is outside of the range for 12 bits!".format(position))
        if byteCount > 0xF:
            raise RuntimeError("{0} is too much for 4 bits.".format(byteCount))
        
        positionNibble = position >> 8
        positionByte = position & 0xFF
        
        byte1 = (byteCount << 4) | positionNibble
        
        return byte1, positionByte
        
        
    # A simple iterator for iterating over the bits of a single byte
    def __bit_iter__(self, byte):
        for i in xrange(8):
            result = (byte << i) & 0x80
            yield result != 0
"""


#
#    Helper Functions for easier usage of
#    the compress & decompress methods of the module.
#

# Take a compressed string, decompress it and return the
# results as a string. 
def decompress__(string):
    stringObj = StringIO(string)
    yaz0obj = yaz0(stringObj, compress = False)
    return yaz0obj.decompress().getvalue()

# Take a file-like object, decompress it and return the
# results as a StringIO object.
def decompress_fileobj(fileobj):
    yaz0obj = yaz0(fileobj, compress = False)
    return yaz0obj.decompress()

# Take a file name and decompress the contents of that file. 
# If outputPath is given, save the results to a file with
# the name defined by outputPath, otherwise return the results
# as a StringIO object.
def decompress_file(filenamePath, outputPath = None):
    with open(filenamePath, "rb") as fileobj:
        yaz0obj = yaz0(fileobj, compress = False)
        
        result = yaz0obj.decompress()
        
        if outputPath != None:
            with open(outputPath, "wb") as output:
                output.write(result.getvalue())
            
            result = None
            
    return result


# Take an uncompressed string, compress it and
# return the results as a string.
def compress(string, compressLevel = 9):
    stringObj = StringIO(string)
    yaz0obj = yaz0(stringObj, compress = True)
    return yaz0obj.compress(compressLevel).getvalue()

# Take a file-like object, compress it and
# return the results as a StringIO object.
def compress_fileobj(fileobj, compressLevel = 9):
    yaz0obj = yaz0(fileobj, compress = True)
    return yaz0obj.compress(compressLevel)

# Take a file name and compress the contents of that file.
# If outputPath is not None, write the results to a file
# with the name defined by outputPath, otherwise return
# results as a StringIO object.
def compress_file(filenamePath, outputPath = None, compressLevel = 9):
    with open(filenamePath, "rb") as fileobj:
        yaz0obj = yaz0(fileobj, compress = True)
        
        result = yaz0obj.compress(compressLevel)
        
        if outputPath != None:
            with open(outputPath, "wb") as output:
                output.write(result.getvalue())
            
            result = None
            
    return result



if __name__ == "__main__":
    compress = True
        
    """if not compress:
        fileobj = open("compressed.dat", "rb")
        yazObj = yaz0(fileobj)
        output = yazObj.decompress()
        fileobj.close()
        
        writefile = open("decompressed.dat", "wb")
        writefile.write(output.getvalue())
        writefile.close()
        
    else:
        start = time()
        fileobj = open("decompressed.dat", "rb")
        yazObj = yaz0(fileobj, compress = True)
        output = yazObj.compress(compressLevel = 9)
        fileobj.close()
        
        writefile = open("compressed.dat", "wb")
        writefile.write(output.getvalue())
        writefile.close()
        
        print "Time taken: {0} seconds".format(time()-start)"""
        
    with open("arc.szs", "rb") as f:
        with open("arcmy.arc", "w+b") as g:
            decompress(f, out=g)
            
    with open("arcmy.arc", "rb") as f:
        with open("arcmy.szs", "w+b") as g:
            compress_fast(f, out=g)
            
    with open("arcmy.szs", "rb") as f:
        with open("arcmydecompressedagain.arc", "w+b") as g:
            decompress(f, out=g)
        