"""Storage for arbitrary python objects inspired by SemiDMB and Shelve.

Data structure and byte sizes are as follows:

⠀⠀⠀8⠀⠀⠀⠀⠀⠀⠀⠀8⠀⠀⠀⠀⠀⠀⠀⠀⠀8⠀⠀⠀⠀⠀⠀x⠀⠀⠀⠀y⠀⠀⠀⠀⠀⠀4⠀⠀⠀⠀⠀⠀⠀⠀⠀8⠀⠀⠀⠀⠀⠀⠀⠀⠀8⠀⠀⠀⠀⠀⠀x⠀⠀⠀⠀y⠀⠀⠀⠀⠀⠀4
<header><key_size><valsize><key><val><checksum><key_size><valsize><key><val><checksum>...
"""

import os
import mmap
import struct
import ctypes
import builtins
import pickle
from itertools import chain

from typing import Literal, Any, Mapping, Iterator, Generator
from binascii import crc32
from ctypes.wintypes import LPVOID, DWORD

__all__ = [
    "open",
    "DBMError",
    "DBMLoadError",
    "DBMChecksumError"
]


class DBMError(Exception):
    pass


class DBMLoadError(DBMError):
    pass


class DBMChecksumError(DBMError):
    pass


# File handing flags
DATA_OPEN_FLAGS = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_BINARY
DATA_OPEN_FLAGS_READONLY = os.O_RDONLY | os.O_BINARY

# File atomic rename stuff
LPCTSTR = ctypes.c_wchar_p
kernel32 = ctypes.windll.kernel32
kernel32.ReplaceFile.argtypes = [LPCTSTR, LPCTSTR, LPCTSTR, DWORD, LPVOID, LPVOID]

DELETED: int = 0
"""Signifies item has been deleated."""

# Header Info
FILE_IDENTIFIER: bytes = b'DBMW'  # \x44\x42\x4d\x57 in hex
"""Magic identifier for this type of file."""
FILE_FORMAT_VERSION: int = 1
"""Version of the file format."""
PICKLE_PROTOCOL: int = 5
"""Pickle protocol used if necessary."""

# Struct (un)packing formats. Make sure that the length in bytes when
# a value is converted by the format string according to this table:
# https://docs.python.org/3/library/struct.html#format-characters
# ... is the same as the size marked here.

HEADER_FORMAT: str = "!4sHH"
HEADER_SIZE: int = 8

CHECKSUM_FORMAT: str = "!I"
CHECKSUM_SIZE: int = 4

KEYVAL_FORMAT: str = "!II"
KEYVAL_SIZE: int = 8


class _DBMWReadOnly:
    """DBMW file in read-only mode, error if doesn't exist."""

    def __init__(self, filename: str, verify_checksums: bool = False):
        """Encapsulate a DBMW file in read-only mode, raises DBMError if file does not exist.

        :param filename: Name of the file to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        """

        if not os.path.isfile(filename):
            raise DBMError(f"Not a file: {filename}")

        self._dbname = filename
        self._data_flags = DATA_OPEN_FLAGS_READONLY
        self._verify_checksums = verify_checksums

        self._index: dict[bytes, tuple[int, int]] = self._load_index(self._dbname)
        """The in memory index. Index 'key' is the name of the stored value in bytes and index 'value' is a tuple 
        of the offset in bytes in the file to the stored value, and the size of the stored value in bytes."""

        self._data_file_descriptor: int = os.open(self._dbname, self._data_flags)
        self._current_offset: int = os.lseek(self._data_file_descriptor, 0, os.SEEK_END)

    def __getitem__(self, key: Any) -> Any:
        """Load value from the db.

        :raises KeyError: Key not found in db.
        :raises pickle.PicklingError: Key is not pickleable.
        """

        key = self._convert_to_bytes(key)

        offset, size = self._index[key]
        os.lseek(self._data_file_descriptor, offset, os.SEEK_SET)

        if not self._verify_checksums:
            return os.read(self._data_file_descriptor, size)
        else:
            data = os.read(self._data_file_descriptor, size + CHECKSUM_SIZE)
            return self._verify_checksum_data(key, data)

    def __iter__(self) -> Iterator[bytes]:
        for key in iter(self._index.keys()):
            yield self._convert_from_bytes(key)

    def __reversed__(self) -> Iterator[bytes]:
        for key in reversed(self._index.keys()):
            yield self._convert_from_bytes(key)

    def __contains__(self, key: Any) -> bool:
        return self._convert_to_bytes(key) in self._index

    def __len__(self):
        return len(self._index)

    def __del__(self):
        if not self._verify_checksums:
            return
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        """Close the db.

        The data is synced to disk and the db is closed.
        Once the db has been closed, no further reads or writes are allowed.
        """

        os.close(self._data_file_descriptor)

    def keys(self) -> list[Any]:
        """Return all they keys in the db."""
        return list(self._index.keys())

    def values(self) -> list[Any]:
        """Return all they values in the db."""
        return [self[key] for key in self._index]

    def items(self) -> list[tuple[Any, Any]]:
        """Return list of key value pairs."""
        return [(key, self[key]) for key in self._index]

    def get(self, key: Any) -> Any:
        """Get value for key in db."""
        return self[key]

    def iter_file_data(self, filename: str) -> Generator[tuple[bytes, int, int], None, None]:
        """Iterate over the stored data.

        Accepts a filename and iterates over the data bytes stored in it.
        Each yielded item should be a tuple of:

        - (key_name, offset, val_size)

        **key_name** is the name of the key (bytes).

        **offset** is the integer offset within the file to the value associated with the key.

        **val_size** is the size of the value in bytes.

        :raises DBMLoadError: Something wrong with the file contents.
        """

        with builtins.open(filename, "rb") as f:
            self._verify_header(header=f.read(HEADER_SIZE))

            offset: int = HEADER_SIZE

            with mmap.mmap(fileno=f.fileno(), length=0, access=mmap.ACCESS_READ) as contents:
                while True:

                    if offset >= len(contents):
                        break  # End of file, so stop reading values

                    try:
                        key_size, val_size = struct.unpack(KEYVAL_FORMAT, contents[offset:offset + KEYVAL_SIZE])
                    except struct.error:
                        raise DBMLoadError(f"Key and value size indicators could not be unpacked from file at position {offset}/{len(contents)}.")

                    offset += KEYVAL_SIZE

                    key_name = contents[offset:offset + key_size]
                    if len(key_name) != key_size:
                        raise DBMLoadError(f"Could not read the whole key.")

                    offset += key_size

                    yield key_name, offset, val_size

                    offset += (val_size + CHECKSUM_SIZE)

    @staticmethod
    def _convert_to_bytes(value: Any) -> bytes:
        """Converts to bytes with either utf-8 encoding or pickle

        :raises pickle.PicklingError: Value is not picklable
        """

        if isinstance(value, bytes):
            return value

        elif isinstance(value, (str, int, float)):
            return str(value).encode("utf-8")

        else:
            return pickle.dumps(value, protocol=PICKLE_PROTOCOL)

    @staticmethod
    def _convert_from_bytes(value: bytes) -> Any:
        """Tries to detect if value was encoded with pickle or utf-8 and decodes value form the bytes.

        :raises: pickle.UnpicklingError: Value is unpicklable.
        """

        #       PROTO                      PICKLE VERSION                        STOP
        #    \x80 -> 128                \x05 -> 5   \x04 -> 4                   . -> 46
        if value[0] == 128 and value[1] in range(1, PICKLE_PROTOCOL + 1) and value[-1] == 46:
            return pickle.loads(value)

        value = value.decode("utf-8")

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        return value

    @staticmethod
    def _verify_header(header: bytes):
        """Check that file is correct type and compatible version.

        :raises DBMLoadError: File was incorrect type or incompatible version.
        """

        signature, file_version, pickling_version = struct.unpack(HEADER_FORMAT, header)

        if signature != FILE_IDENTIFIER:
            raise DBMLoadError("File is not a DBMW db file.")
        if file_version != FILE_FORMAT_VERSION:
            raise DBMLoadError(f"Incompatible file version (got: v{file_version}, can handle: v{FILE_FORMAT_VERSION})")
        if pickling_version < PICKLE_PROTOCOL:
            raise DBMLoadError(f"Incompatible pickling protocol. (got: v{pickling_version}, requires: v{PICKLE_PROTOCOL})")

    @staticmethod
    def _verify_checksum_data(key: bytes, data: bytes) -> bytes:
        """Verify the data by calculating the checksum with CRC-32. Return data without the checksum.

        :raises DBMChecksumError: Checksum failed.
        """

        data_no_checksum = data[:-CHECKSUM_SIZE]
        checksum = struct.unpack(CHECKSUM_FORMAT, data[-CHECKSUM_SIZE:])[0]
        computed_checksum = crc32(key + data_no_checksum)

        if computed_checksum != checksum:
            raise DBMChecksumError(f"Corrupt data detected: invalid checksum for key {key}.")

        return data_no_checksum

    def _load_index(self, filename: str) -> dict[bytes, tuple[int, int]]:
        """This method is only used upon instantiation to populate the in memory index."""
        index = {}

        for key_name, offset, val_size in self.iter_file_data(filename):
            if val_size == DELETED:
                # Due to the append only nature of the db, when values would be deleted from the file,
                # a new dataint is appended to the file with the same key but the value size set to 'DELETED' instead.
                # This means that if val_size is DELETED, there must be a value with the same key already in the index,
                # but it should not be included, as it's marked deleted here.
                del index[key_name]
            else:
                index[key_name] = (offset, val_size)

        return index


class _DBMWCreate(_DBMWReadOnly):
    """DBMW file in read-write more, create if doesn't exist."""

    def __init__(self, filename: str, verify_checksums: bool = False, compact: bool = False):  # noqa
        """Encapsulate a DBMW file in read-write mode, creating a new database if none exists with given filename.

        :param filename: Name of the file to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param compact: Indicate whether or not to compact the db before closing the db.
        """

        self._dbname = filename
        self._compact = compact
        self._data_flags = DATA_OPEN_FLAGS
        self._verify_checksums = verify_checksums

        self._index: dict[bytes, tuple[int, int]] = self._load_index(self._dbname)
        """The in memory index. Dictionary Key is the offset in bytes in the file to the stored value, 
        and Value indicates the size of the stored value in bytes."""

        self._data_file_descriptor: int = os.open(self._dbname, self._data_flags)
        self._current_offset: int = os.lseek(self._data_file_descriptor, 0, os.SEEK_END)

    def __setitem__(self, key: Any, value: Any):
        """Save value in the db.

        :raises pickle.PicklingError: Key is not pickleable.
        """

        key = self._convert_to_bytes(key)
        value = self._convert_to_bytes(value)

        # Write the new data out at the end of the file. Format is:
        # <key_size><valsize><key><val><checksum>

        key_size = len(key)
        val_size = len(value)

        keyval_size = struct.pack(KEYVAL_FORMAT, key_size, val_size)
        keyval = key + value

        checksum = struct.pack(CHECKSUM_FORMAT, crc32(keyval))

        blob = keyval_size + keyval + checksum
        os.write(self._data_file_descriptor, blob)

        # Update the in memory index.
        self._index[key] = (self._current_offset + KEYVAL_SIZE + key_size, val_size)
        self._current_offset += len(blob)

    def __delitem__(self, key: Any):
        """Write new value to the file marking that a certain key has been deleted and remove it from the index.
        When the file is loaded after this, it sees that the value is marked deleted and won't add it to the index.
        Still, if a value is added later under the same key, that value will be added to the index.

        :raises KeyError: Key not found in db.
        :raises pickle.PicklingError: Key is not pickleable.
        """

        key = self._convert_to_bytes(key)

        del self._index[key]

        # Write DELETED as the size of the deleted item. Format is:
        # <keysize><DELETED><key><checksum>

        key_size = struct.pack(KEYVAL_FORMAT, len(key), DELETED)
        checksum = struct.pack(CHECKSUM_FORMAT, crc32(key))

        blob = key_size + key + checksum
        os.write(self._data_file_descriptor, blob)

        self._current_offset += len(blob)

    def close(self, compact: bool = False):
        """Close the db.

        The data is synced to disk and the db is closed.
        Once the db has been closed, no further reads or writes are allowed.

        :param compact: Enable compaction here, even if it was not enabled by open.
        """

        if self._compact or compact:
            self.compact()

        self.sync()
        os.close(self._data_file_descriptor)

    def sync(self):
        """Sync the db to disk.

        This will flush any of the existing buffers and fsync the data to disk.

        You should call this method to guarantee that the data is written to disk.
        This method is also called whenever the dbm is `close()`'d.
        """

        # The files are opened unbuffered so we don't technically need to flush the file objects.
        os.fsync(self._data_file_descriptor)

    def compact(self):
        """Rewrite the contents of the files.

        This method is needed because of the append only nature of the db.
        Basically, compaction works by opening a new db, writing all the keys from this db to the new db, renaming the
        new db to the filenames associated with this db, and reopening the new db as this db.

        Compaction is optional, since it's a trade-off between speed and storage space used.
        As a general rule of thumb, the more non-read updates you do, the more space you'll save when you compact.
        """

        # Copy the file and close it and the current file
        new_db = self.copy(self._dbname + "_copy")
        new_db.close()
        os.close(self._data_file_descriptor)

        # Rename the new file to the current file, replacing it in the process.
        self._rename(from_file=new_db._dbname, to_file=self._dbname)

        # Open the new file as the current file.
        self._index: dict[bytes, tuple[int, int]] = new_db._index
        self._data_file_descriptor: int = os.open(self._dbname, self._data_flags)
        self._current_offset: int = new_db._current_offset

    def clear(self):
        """Delete all data from the db."""
        for key in self._index:
            self.pop(key)
        self._index = {}
        self.compact()

    def setdefault(self, key: Any, default: Any = None):
        """If key is in the db, return its value. If not, insert key with a value of default and return default."""

        if key in self._index:
            return self._index[key]
        else:
            self[key] = default
            return default

    def pop(self, key: Any, default: Any = None):
        """If key is in the db, remove it and return its value, else return default if not None.

        :raises KeyError: Default is not given and key is not in the dictionary
        """

        try:
            value = self[key]
            del self[key]
            return value
        except KeyError as key_e:
            if default is not None:
                return default
            else:
                raise key_e

    def popitem(self) -> tuple[Any, Any]:
        """Get last inserted key value pair."""
        key, value = self._index.popitem()
        self._index[key] = value
        value = self.pop(key)
        return key, value

    def copy(self, new_filename: str):
        """Creates a copy of this db by writing all the keys from this db to the new db."""

        assert new_filename != self._dbname, "Copy can't have the same filename as the original."

        new_db = self.__class__(filename=new_filename, verify_checksums=self._verify_checksums, compact=self._compact)

        for key in self._index:
            new_db[key] = self[key]

        return new_db

    def update(self, other: Mapping[Any, Any], **kwargs: Any):
        """Update db with the the keys and value in other or with given kwargs.
        If both are present, kwargs will overwrite keys given in other."""

        for key, value in chain(other, kwargs):
            self[key] = value

    @staticmethod
    def _rename(from_file: str, to_file: str):
        """Similar to os.rename(), but that doesn't work if the 'to_file'
        exists so we have to use our own version that supports atomic renames.

        :raises OSError: File can't be renamed.
        """

        rc = kernel32.ReplaceFile(LPCTSTR(to_file), LPCTSTR(from_file), None, 0, None, None)
        if rc == 0:
            raise OSError(f"Can't rename file, error: {kernel32.GetLastError()}")

    @staticmethod
    def _write_headers(filename: str):
        """Write the 8-bit header onto the file."""

        with builtins.open(filename, "wb") as f:
            f.write(struct.pack(HEADER_FORMAT, FILE_IDENTIFIER, FILE_FORMAT_VERSION, PICKLE_PROTOCOL))

    def _load_index(self, filename: str) -> dict[bytes, tuple[int, int]]:
        """This method is only used upon instantiation to populate the in memory index."""

        if not os.path.isfile(filename):
            self._write_headers(filename)
            return {}

        return super(_DBMWCreate, self)._load_index(filename)


class _DBMWReadWrite(_DBMWCreate):
    """DBMW file in read-write mode, error if doesn't exist."""

    def __init__(self, filename: str, verify_checksums: bool = False, compact: bool = False):
        """Encapsulate a DBMW file in read-write mode, raises DBMError if file does not exist.

        :param filename: Name of the file to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param compact: Indicate whether or not to compact the db before closing the db.
        """

        if not os.path.isfile(filename):
            raise DBMError(f"Not a file: {filename}")

        super(_DBMWReadWrite, self).__init__(filename=filename, verify_checksums=verify_checksums, compact=compact)


class _DBMWNew(_DBMWCreate):
    """DBMW File will always be created, even if one exists."""

    def __init__(self, filename: str, verify_checksums: bool = False, compact: bool = False):
        """Encapsulate a DBMW file in read-write mode, creating a new file even if one exists for given filename.

        :param filename: Name of the file to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param compact: Indicate whether or not to compact the db before closing the db.
        """

        if os.path.exists(filename):
            os.remove(filename)

        super(_DBMWNew, self).__init__(filename=filename, verify_checksums=verify_checksums, compact=compact)



def open(filename: str, flag: Literal["r", "w", "c", "n"] = "r", verify_checksums: bool = False, compact: bool = False):  # noqa
    """Open a DBMW database.

    :param filename: The name of the db.
    :param flag: Specifies how the db should be opened.
                 'r' = Open existing database for reading only (default).
                 'w' = Open existing database for reading and writing.
                 'c' = Open database for reading and writing, creating it if it doesn't exist.
                 'n' = Always create a new, empty database, open for reading and writing.
    :param verify_checksums: Verify the checksums for each value are correct on every __getitem__ call
    :param compact: Indicate whether or not to compact the db before closing it. No effect in read only mode.
    :raises ValueError: Flag argument incorrect.
    """

    if flag == "r":
        return _DBMWReadOnly(filename, verify_checksums=verify_checksums)
    elif flag == "w":
        return _DBMWReadWrite(filename, verify_checksums=verify_checksums, compact=compact)
    elif flag == "c":
        return _DBMWCreate(filename, verify_checksums=verify_checksums, compact=compact)
    elif flag == "n":
        return _DBMWNew(filename, verify_checksums=verify_checksums, compact=compact)
    else:
        raise ValueError("Flag argument must be 'r', 'c', 'w', or 'n'")
