"""DBM key value storage for windows inspired by semidb."""

import os
import sys
import mmap
import struct
import ctypes
from ctypes.wintypes import LPVOID, DWORD
import builtins

file_open = builtins.open
str_type = str


class DBMError(Exception):
    pass


class DBMLoadError(DBMError):
    pass


class DBMChecksumError(DBMError):
    pass


DATA_OPEN_FLAGS = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_BINARY
DATA_OPEN_FLAGS_READONLY = os.O_RDONLY | os.O_BINARY

LPCTSTR = ctypes.c_wchar_p
LPTSTR = LPCTSTR
kernel32 = ctypes.windll.kernel32
kernel32.ReplaceFile.argtypes = [LPCTSTR, LPCTSTR, LPCTSTR, DWORD, LPVOID, LPVOID]

_MAPPED_LOAD_PAGES = 300
FILE_FORMAT_VERSION = (1, 1)
FILE_IDENTIFIER = b"\x53\x45\x4d\x49"
_DELETED = -1



def rename(src, dst):
    rc = kernel32.ReplaceFile(LPCTSTR(dst), LPCTSTR(src), None, 0, None, None)
    if rc == 0:
        raise OSError("can't rename file, error: %s" % kernel32.GetLastError())



class DBMLoader:

    @staticmethod
    def _verify_header(header):
        """Check that file is correct type."""

        signature = header[:4]
        if signature != FILE_IDENTIFIER:
            raise DBMLoadError("File is not a semidbm db file.")

        major, minor = struct.unpack("!HH", header[4:])
        if major != FILE_FORMAT_VERSION[0]:
            raise DBMLoadError(f"Incompatible file version (got: v{major}, can handle: v{FILE_FORMAT_VERSION[0]})")

    def iter_keys(self, filename):
        """Load the keys given a filename.

        Accepts a filename and iterates over the keys associated with the data file.
        Each yielded item should contain a tuple of:

        - (key_name, offset, size)

        where key_name is the name of the key (bytes), offset is the integer
        offset within the file of the value associated with the key, and size
        is the size of the value in bytes.
        """

        # yields keyname, offset, size
        with open(filename, "rb") as f:
            header = f.read(8)

        f = open(filename, "rb")

        self._verify_header(header)


        contents = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        remap_size = mmap.ALLOCATIONGRANULARITY * _MAPPED_LOAD_PAGES

        # We need to track the max_index to use as the upper bound
        # in the .find() calls to be compatible with python 2.6.
        # There's a bug in python 2.6 where if an offset is specified
        # along with a size of 0, then the size for mmap() is the size
        # of the file instead of the size of the file - offset.  To
        # fix this, we track this ourself and make sure we never go passed
        # max_index.  If we don't do this, python2.6 will crash with
        # a bus error (python2.7 works fine without this workaround).
        # See http://bugs.python.org/issue10916 for more info.
        max_index = os.path.getsize(filename)

        file_size_bytes = max_index
        num_resizes = 0
        current = 8

        try:
            while current != max_index:
                try:
                    key_size, val_size = struct.unpack(
                        "!ii", contents[current: current + 8]
                    )
                except struct.error:
                    raise DBMLoadError()
                key = contents[current + 8 : current + 8 + key_size]
                if len(key) != key_size:
                    raise DBMLoadError()
                offset = (remap_size * num_resizes) + current + 8 + key_size
                if offset + val_size > file_size_bytes:
                    # If this happens then the index is telling us
                    # to read past the end of the file.  What we need
                    # to do is stop reading from the index.
                    return
                yield key, offset, val_size
                if val_size == _DELETED:
                    val_size = 0
                # Also need to skip past the 4 byte checksum, hence
                # the '+ 4' at the end
                current = current + 8 + key_size + val_size + 4
                if current >= remap_size:
                    contents.close()
                    num_resizes += 1
                    offset = num_resizes * remap_size
                    # Windows python2.6 bug.  You can't specify a length of
                    # 0 with an offset, otherwise you get a WindowsError, not
                    # enough storage is available to process this command.
                    # Couldn't find an issue for this, but the workaround
                    # is to specify the actual length of the mmap'd region
                    # which is the total size minus the offset we want.
                    contents = mmap.mmap(
                        f.fileno(),
                        file_size_bytes - offset,
                        access=mmap.ACCESS_READ,
                        offset=offset,
                    )
                    current -= remap_size
                    max_index -= remap_size
        finally:
            contents.close()
            f.close()













