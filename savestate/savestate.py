"""Persistent storage for arbitrary python objects inspired by SemiDBM and Shelve.

Data structure and byte sizes are as follows:
⠀\n
⠀\n
Header:⠀<file_identifier: 9 bytes> <file_format_version: 2 bytes> <pickle_version: 2 bytes>\n
Data:⠀⠀⠀<keysize: 4 bytes> <valsize: 4 bytes> <key: 'keysize' bytes> <val: 'valsize' bytes> <checksum: 4 bytes>\n
⠀⠀⠀⠀⠀⠀⠀⠀<keysize: 4 bytes> <valsize: 4 bytes> <key: 'keysize' bytes> <val: 'valsize' bytes> <checksum: 4 bytes>\n
⠀⠀⠀⠀⠀⠀⠀⠀...\n
⠀\n
"""

import os
import sys
import mmap
import uuid
import ntpath
import struct
import builtins
import pickle
import warnings

from typing import Literal, Any, Mapping, Iterator, Generator
from binascii import crc32

__all__ = [
    "open",
    "SaveStateError",
    "SaveStateLoadError",
    "SaveStateChecksumError"
]


class SaveStateError(Exception):
    pass


class SaveStateLoadError(SaveStateError):
    pass


class SaveStateChecksumError(SaveStateError):
    pass


# File handing flags
if sys.platform.startswith("win"):
    DATA_OPEN_FLAGS = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_BINARY
    DATA_OPEN_FLAGS_READONLY = os.O_RDONLY | os.O_BINARY
else:
    DATA_OPEN_FLAGS = os.O_RDWR | os.O_CREAT | os.O_APPEND
    DATA_OPEN_FLAGS_READONLY = os.O_RDONLY

DELETED: int = 0
"""Signifies item has been deleated."""

# Header Info
FILE_IDENTIFIER: bytes = b'savestate'
"""Magic identifier for this type of file."""
FILE_FORMAT_VERSION: int = 1
"""Version of the file format."""
PICKLE_PROTOCOL: int = 5
"""Pickle protocol used if necessary."""

# Struct (un)packing formats. Make sure that the length in bytes when
# a value is converted by the format string according to this table:
# https://docs.python.org/3/library/struct.html#format-characters
# ... is the same as the size marked here.
HEADER_FORMAT: str = "!9sHH"
HEADER_SIZE: int = 13
CHECKSUM_FORMAT: str = "!I"
CHECKSUM_SIZE: int = 4
KEYVAL_IND_FORMAT: str = "!II"
KEYVAL_IND_SIZE: int = 8


class _SaveStateReadOnly:
    """SaveState file in read-only mode, error if doesn't exist."""

    def __init__(self, filename: str, verify_checksums: bool = False, dbm_mode: bool = False):
        """Encapsulate a SaveState file in read-only mode, raises SaveStateError if savestate does not exist.

        :param filename: Name of the savestate to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param dbm_mode: Operate in dbm mode. This is faster, but only allows strings for keys and values.
        """

        if not os.path.isfile(filename):
            raise SaveStateError(f"Not a file: {filename}")

        self._savestate_name = filename
        self._dbm_mode = dbm_mode
        self._data_flags = DATA_OPEN_FLAGS_READONLY
        self._verify_checksums = verify_checksums

        self._index: dict[bytes, tuple[int, int]] = self._load_index(self._savestate_name)
        """The in memory index. Index 'key' is the name of the stored value in bytes and index 'value' is a tuple 
        of the offset in bytes in the file to the stored value, and the size of the stored value in bytes."""

        self._data_file_descriptor: int = os.open(self._savestate_name, self._data_flags)
        self._current_offset: int = os.lseek(self._data_file_descriptor, 0, os.SEEK_END)

    def __repr__(self) -> str:
        selftype = type(self)
        flag = ""
        if selftype == _SaveStateReadOnly:
            flag = "r"
        elif selftype == _SaveStateReadWrite:
            flag = "w"
        elif selftype == _SaveStateCreate:
            flag = "c"
        elif selftype == _SaveStateNew:
            flag = "n"

        if hasattr(self, "_compact"):
            return f"savestate.open(filename={self._savestate_name}, flag={flag}, " \
                   f"verify_checksums={self._verify_checksums}, compact={self._compact}, dbm_mode={self._dbm_mode})"
        else:
            return f"savestate.open(filename={self._savestate_name}, flag={flag}, " \
                   f"verify_checksums={self._verify_checksums}, dbm_mode={self._dbm_mode})"

    def __str__(self) -> str:
        return "SaveState file with content: {" + ", ".join([f"'{key}': '{value}'" for key, value in self.items()]) + "}"

    def __getitem__(self, key: Any) -> Any:
        """Load value from the savestate.

        :raises KeyError: Key not found in the savestate.
        :raises AttributeError: Savestate closed.
        :raises pickle.PicklingError: Key is not pickleable.
        """

        if self._dbm_mode:
            key = key.encode() if isinstance(key, str) else key
        else:
            key = self._convert_to_bytes(key)

        offset, size = self._index[key]
        os.lseek(self._data_file_descriptor, offset, os.SEEK_SET)

        if not self._verify_checksums:
            data = os.read(self._data_file_descriptor, size)
        else:
            data = os.read(self._data_file_descriptor, size + CHECKSUM_SIZE)
            data = self._verify_data_checksum(key, data)

        if self._dbm_mode:
            return data
        else:
            return self._convert_from_bytes(data)

    def __iter__(self) -> Iterator[bytes]:
        for key in iter(self._index.keys()):
            yield self._convert_from_bytes(key)

    def __reversed__(self) -> Iterator[bytes]:
        for key in reversed(self._index.keys()):
            yield self._convert_from_bytes(key)

    def __contains__(self, key: Any) -> bool:
        if self._dbm_mode:
            return key.encode() if isinstance(key, str) else key in self._index
        else:
            return self._convert_to_bytes(key) in self._index

    def __len__(self):
        return len(self._index)

    def __del__(self):
        if not self.is_open:
            return  # already closed or init failed
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    @property
    def filepath(self) -> str:
        return os.path.abspath(self._savestate_name)

    @property
    def filename(self) -> str:
        return ntpath.basename(self._savestate_name)

    @property
    def is_open(self) -> bool:
        return hasattr(self, "_data_file_descriptor")

    def close(self):
        """Close the savestate.

        The data is synced to disk and the savestate is closed.
        Once the savestate has been closed, no further reads or writes are allowed.

        :raises AttributeError: Savestate closed.
        """

        os.close(self._data_file_descriptor)
        # Should be deleted to indicate file is closed to __del__
        delattr(self, "_data_file_descriptor")

    def keys(self) -> list[Any]:
        """Return all they keys in the savestate."""
        return [self._convert_from_bytes(key) for key in self._index]

    def values(self) -> list[Any]:
        """Return all they values in the savestate."""
        return [self[self._convert_from_bytes(key)] for key in self._index]

    def items(self) -> list[tuple[Any, Any]]:
        """Return list of key value pairs."""
        return [(self._convert_from_bytes(key), self[self._convert_from_bytes(key)]) for key in self._index]

    def get(self, key: Any, default: Any = None) -> Any:
        """Get value for key in savestate."""
        return self[key] if key in self else default

    def _iter_file_data(self, filename: str) -> Generator[tuple[bytes, int, int], None, None]:
        """Iterate over the stored data.

        Accepts a filename and iterates over the data bytes stored in it.
        Each yielded item should be a tuple of:

        - (key_name, offset, val_size)

        **key_name** is the name of the key (bytes).

        **offset** is the integer offset within the file to the value associated with the key.

        **val_size** is the size of the value in bytes.

        :raises SaveStateError: Something wrong with the file contents.
        """

        with builtins.open(filename, "rb") as f:
            self._verify_header(header=f.read(HEADER_SIZE))

            offset: int = HEADER_SIZE
            needed_bytes: int = 0

            with mmap.mmap(fileno=f.fileno(), length=0, access=mmap.ACCESS_READ) as contents:
                while True:

                    if offset >= len(contents):
                        break  # End of file, so stop reading values

                    try:
                        key_size, val_size = struct.unpack(KEYVAL_IND_FORMAT, contents[offset:offset + KEYVAL_IND_SIZE])
                        if key_size < 1:
                            warnings.warn(f"Improper key length '{key_size}' at position {offset}/{len(contents)}. "
                                          f"Could not continue to read data.", category=BytesWarning)
                            break
                        elif val_size < 0:
                            warnings.warn(f"Improper key length '{val_size}' at position {offset + KEYVAL_IND_SIZE / 2}/{len(contents)}. "
                                          f"Could not continue to read data.", category=BytesWarning)
                            break
                    except struct.error:
                        warnings.warn(f"Key and value size indicators could not be unpacked from file "
                                      f"at position {offset}/{len(contents)}.", category=BytesWarning)
                        break

                    needed_bytes = (offset + KEYVAL_IND_SIZE + key_size + val_size + CHECKSUM_SIZE) - len(contents)
                    if needed_bytes > 0:
                        warnings.warn(f"Some of the data is missing at the end of the file. Compaction necessary.", category=BytesWarning)
                        break

                    offset += KEYVAL_IND_SIZE
                    key = contents[offset:offset + key_size]
                    offset += key_size

                    try:
                        self._verify_data_checksum(key, data_with_checksum=contents[offset:offset + val_size + CHECKSUM_SIZE])
                        yield key, offset, val_size

                    except SaveStateChecksumError:
                        warnings.warn(f"Data was corrupted at position {offset}/{len(contents)}. Compaction necessary.", category=BytesWarning)

                    offset += (val_size + CHECKSUM_SIZE)

        # If file doesn't have enought bytes, fill with blank data to
        # recover from errors that would arise when writing more data to the file.
        if needed_bytes > 0:
            with builtins.open(filename, "ab+") as f:
                f.write(b"\x00" * needed_bytes)

    def _load_index(self, filename: str) -> dict[bytes, tuple[int, int]]:
        """This method is only used upon instantiation to populate the in memory index."""
        index = {}

        for key, offset, val_size in self._iter_file_data(filename):
            if val_size == DELETED:
                # Due to the append only nature of savestate, when values would be deleted from the file,
                # a new datapoint is appended to the file with the same key but the value size set to 'DELETED' instead.
                # This means that if val_size is DELETED, there must be a value with the same key already in the index,
                # but it should not be included, as it's marked deleted here.
                del index[key]
            else:
                index[key] = offset, val_size

        return index

    @staticmethod
    def _convert_to_bytes(value: Any) -> bytes:
        return pickle.dumps(value, protocol=PICKLE_PROTOCOL)

    @staticmethod
    def _convert_from_bytes(value: bytes) -> Any:
        return pickle.loads(value)

    @staticmethod
    def _verify_header(header: bytes):
        """Check that file is correct type and compatible version.

        :raises SaveStateError: File was incorrect type or incompatible version.
        """

        signature, file_version, pickling_version = struct.unpack(HEADER_FORMAT, header)

        if signature != FILE_IDENTIFIER:
            raise SaveStateLoadError("File is not a SaveState file.")
        if file_version != FILE_FORMAT_VERSION:
            raise SaveStateLoadError(f"Incompatible file version (got: v{file_version}, can handle: v{FILE_FORMAT_VERSION})")
        if pickling_version < PICKLE_PROTOCOL:
            raise SaveStateLoadError(f"Incompatible pickling protocol. (got: v{pickling_version}, requires: v{PICKLE_PROTOCOL})")

    @staticmethod
    def _verify_data_checksum(key: bytes, data_with_checksum: bytes) -> bytes:
        """Verify the data by calculating the checksum with CRC-32. Return data without the checksum.

        :raises SaveStateChecksumError: Checksum failed.
        """

        data_no_checksum = data_with_checksum[:-CHECKSUM_SIZE]
        checksum = struct.unpack(CHECKSUM_FORMAT, data_with_checksum[-CHECKSUM_SIZE:])[0]
        computed_checksum = crc32(key + data_no_checksum)

        if computed_checksum != checksum:
            raise SaveStateChecksumError(f"Corrupt data detected: invalid checksum for key {key}.")

        return data_no_checksum


class _SaveStateCreate(_SaveStateReadOnly):
    """SaveState file in read-write more, create if doesn't exist."""

    def __init__(self, filename: str, verify_checksums: bool = False, compact: bool = False, dbm_mode: bool = False):  # noqa
        """Encapsulate a SaveState file in read-write mode, creating a new savestate if none exists with given filename.

        :param filename: Name of the savestate to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param compact: Indicate whether or not to compact the savestate before closing the it.
        :param dbm_mode: Operate in dbm mode. This is faster, but only allows strings for keys and values.
        """

        self._savestate_name = filename
        self._dbm_mode = dbm_mode
        self._compact = compact
        self._data_flags = DATA_OPEN_FLAGS
        self._verify_checksums = verify_checksums

        self._index: dict[bytes, tuple[int, int]] = self._load_index(self._savestate_name)
        """The in memory index. Index 'key' is the name of the stored value in bytes and index 'value' is a tuple 
        of the offset in bytes in the file to the stored value, and the size of the stored value in bytes."""

        self._data_file_descriptor: int = os.open(self._savestate_name, self._data_flags)
        self._current_offset: int = os.lseek(self._data_file_descriptor, 0, os.SEEK_END)

    def __setitem__(self, key: Any, value: Any):
        """Save value in the savestate.

        :raises AttributeError: Savestate closed.
        :raises pickle.PicklingError: Key is not pickleable.
        """

        if self._dbm_mode:
            key = key.encode() if isinstance(key, str) else key
            value = value.encode() if isinstance(value, str) else value
        else:
            key = self._convert_to_bytes(key)
            value = self._convert_to_bytes(value)

        key_size = len(key)
        val_size = len(value)

        keyval_size = struct.pack(KEYVAL_IND_FORMAT, key_size, val_size)
        keyval = key + value

        checksum = struct.pack(CHECKSUM_FORMAT, crc32(keyval))

        blob = keyval_size + keyval + checksum
        os.write(self._data_file_descriptor, blob)

        # Update the in memory index.
        self._index[key] = (self._current_offset + KEYVAL_IND_SIZE + key_size, val_size)
        self._current_offset += len(blob)

    def __delitem__(self, key: Any):
        """Write new value to the savestate marking that a certain key has been deleted and remove it from the index.
        When the savestate is loaded after this, it sees that the value is marked deleted and won't add it to the index.
        Still, if a value is added later under the same key, that value will be added to the index.

        :raises KeyError: Key not found in savestate.
        :raises AttributeError: Savestate closed.
        :raises pickle.PicklingError: Key is not pickleable.
        """

        if self._dbm_mode:
            key = key.encode() if isinstance(key, str) else key
        else:
            key = self._convert_to_bytes(key)

        del self._index[key]

        key_size = struct.pack(KEYVAL_IND_FORMAT, len(key), DELETED)
        checksum = struct.pack(CHECKSUM_FORMAT, crc32(key))

        blob = key_size + key + checksum
        os.write(self._data_file_descriptor, blob)

        self._current_offset += len(blob)

    def close(self, compact: bool = False):
        """Close the savestate.

        The data is synced to disk and the savestate is closed.
        Once the savestate has been closed, no further reads or writes are allowed.

        :param compact: Enable compaction here, even if it was not enabled by open.
        :raises AttributeError: Savestate closed.
        """

        if self._compact or compact:
            self.compact()

        self.sync()
        super().close()

    def sync(self):
        """Sync the savestate to disk.

        This will flush any of the existing buffers and fsync the data to disk.

        You should call this method to guarantee that the data is written to disk.
        This method is also called whenever the savestate is `close()`'d.

        :raises AttributeError: Savestate closed.
        """

        # The files are opened unbuffered so we don't technically need to flush the file objects.
        os.fsync(self._data_file_descriptor)

    def compact(self):
        """Rewrite the contents of the savestate file.

        This method is needed because of the append only nature of the file format.
        Basically, compaction works by opening a new savestate, writing all the keys from this savestate to the new savestate, renaming the
        new savestate to the filename associated with this savestate, and reopening the new savestate as this savestate.

        Compaction is optional, since it's a trade-off between speed and storage space used.
        As a general rule of thumb, the more non-read updates you do, the more space you'll save when you compact.
        """

        # Copy the file and close it and the current file
        new_filename = self._savestate_name[:-len(FILE_IDENTIFIER) - 1] + f"_{uuid.uuid4()}"
        new_savestate = self.copy(new_filename)
        new_savestate.close()
        os.close(self._data_file_descriptor)

        # Rename the new file to the current file, replacing it in the process.
        self._rename(from_file=new_savestate._savestate_name, to_file=self._savestate_name)

        # Open the new file as the current file.
        self._index: dict[bytes, tuple[int, int]] = new_savestate._index
        self._data_file_descriptor: int = os.open(self._savestate_name, self._data_flags)
        self._current_offset: int = new_savestate._current_offset

    def clear(self):
        """Delete all data from the savestate."""
        for key in self.keys():
            self.pop(key)
        self._index = {}
        self.compact()

    def setdefault(self, key: Any, default: Any = None):
        """If key is in the savestate, return its value. If not, insert key with a value of default and return default."""

        if self._dbm_mode:
            contains = key.encode() if isinstance(key, str) else key in self._index
        else:
            contains = self._convert_to_bytes(key) in self._index

        if contains:
            return self[key]
        else:
            self[key] = default
            return default

    def pop(self, key: Any, default: Any = None):
        """If key is in the savestate, remove it and return its value, else return default if not None.

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
        """Get last inserted key value pair.

        :raises KeyError: Savestate empty.
        """
        key, value = self._index.popitem()
        self._index[key] = value
        key = self._convert_from_bytes(key)
        value = self.pop(key)
        return key, value

    def copy(self, new_filename: str):
        """Creates a copy of this savestate by writing all the keys from this savestate to the new savestate."""

        new_filename = _add_file_identifier(new_filename)
        assert new_filename != self._savestate_name, "Copy can't have the same filename as the original."

        new_savestate = self.__class__(filename=new_filename, verify_checksums=self._verify_checksums, compact=self._compact)

        for key in iter(self):  # Gives keys converted from bytes
            new_savestate[key] = self[key]

        return new_savestate

    def update(self, other: Mapping[Any, Any], **kwargs: Any):
        """Update the savestate with the the keys and value in other or with given kwargs.
        If both are present, kwargs will overwrite keys given in other."""

        for key, value in other.items():
            self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    @staticmethod
    def _rename(from_file: str, to_file: str):
        """Renames the savestate file. If 'to_file' exists, the savestate file will replace it.

        :raises OSError: File can't be renamed. Possibly being used by another process.
        """

        if sys.platform.startswith("win"):
            import ctypes
            from ctypes.wintypes import LPVOID, DWORD

            LPCTSTR = ctypes.c_wchar_p
            kernel32 = ctypes.windll.kernel32
            kernel32.ReplaceFile.argtypes = [LPCTSTR, LPCTSTR, LPCTSTR, DWORD, LPVOID, LPVOID]

            rc = kernel32.ReplaceFile(LPCTSTR(to_file), LPCTSTR(from_file), None, 0, None, None)
            if rc == 0:
                raise OSError(f"Can't rename file, error: {kernel32.GetLastError()}")

        else:
            os.rename(from_file, to_file)

    @staticmethod
    def _write_headers(filename: str):
        """Write the header onto the file."""

        with builtins.open(filename, "wb") as f:
            f.write(struct.pack(HEADER_FORMAT, FILE_IDENTIFIER, FILE_FORMAT_VERSION, PICKLE_PROTOCOL))

    def _load_index(self, filename: str) -> dict[bytes, tuple[int, int]]:
        """This method is only used upon instantiation to populate the in memory index."""

        if not os.path.isfile(filename):
            self._write_headers(filename)
            return {}

        return super(_SaveStateCreate, self)._load_index(filename)


class _SaveStateReadWrite(_SaveStateCreate):
    """SaveState file in read-write mode, error if doesn't exist."""

    def __init__(self, filename: str, verify_checksums: bool = False, compact: bool = False, dbm_mode: bool = False):
        """Encapsulate a SaveState file in read-write mode, raises SaveStateError if savestate does not exist.

        :param filename: Name of the savestate to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param compact: Indicate whether or not to compact the savestate before closing the savestate.
        :param dbm_mode: Operate in dbm mode. This is faster, but only allows strings for keys and values.
        """

        if not os.path.isfile(filename):
            raise SaveStateError(f"Not a file: {filename}")

        super(_SaveStateReadWrite, self).__init__(filename=filename, verify_checksums=verify_checksums, compact=compact, dbm_mode=dbm_mode)

    def copy(self, new_filename: str):
        # File needs to be opened in 'create' mode so that '__init__' does not raise 'SaveStateError' for the copy.
        # After copying, both of them can be closed and opened in 'read-write' mode.

        new_filename = _add_file_identifier(new_filename)
        assert new_filename != self._savestate_name, "Copy can't have the same filename as the original."

        self.close()
        same_savestate = open(filename=self._savestate_name, flag="c", verify_checksums=self._verify_checksums, compact=self._compact)
        new_savestate = same_savestate.copy(new_filename=new_filename)
        same_savestate.close()
        new_savestate.close()

        super(_SaveStateReadWrite, self).__init__(filename=self._savestate_name, verify_checksums=self._verify_checksums, compact=self._compact)
        new_savestate = open(filename=new_filename, flag="w", verify_checksums=self._verify_checksums, compact=self._compact)

        return new_savestate


class _SaveStateNew(_SaveStateCreate):
    """SaveState File will always be created, even if one exists."""

    def __init__(self, filename: str, verify_checksums: bool = False, compact: bool = False, dbm_mode: bool = False):
        """Encapsulate a SaveState file in read-write mode, creating a new savestate even if one exists for given filename.

        :param filename: Name of the savestate to open.
        :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call.
        :param compact: Indicate whether or not to compact the savestate before closing the it.
        :param dbm_mode: Operate in dbm mode. This is faster, but only allows strings for keys and values.
        """

        if os.path.isfile(filename):
            os.remove(filename)

        super(_SaveStateNew, self).__init__(filename=filename, verify_checksums=verify_checksums, compact=compact, dbm_mode=dbm_mode)


def _add_file_identifier(filename: str) -> str:
    """Adds SaveState file identifier to string."""
    filetype = f".{FILE_IDENTIFIER.decode()}"
    if filename[-len(FILE_IDENTIFIER) - 1:].lower() != filetype:
        filename += filetype
    return filename


def open(filename: str, flag: Literal["r", "w", "c", "n"] = "r", verify_checksums: bool = False, compact: bool = False, dbm_mode: bool = False):  # noqa
    """Open a Savestate.

    :param filename: The name of the savestate to open.
    :param flag: Specifies how the savestate should be opened.
                 'r' = Open existing savestate for reading only (default).
                 'w' = Open existing savestate for reading and writing.
                 'c' = Open savestate for reading and writing, creating it if it doesn't exist.
                 'n' = Always create a new, empty savestate, open for reading and writing.
    :param verify_checksums: Verify that the checksums for each value are correct on every __getitem__ call
    :param compact: Indicate whether or not to compact the savestate before closing it. No effect in read only mode.
    :param dbm_mode: Operate in dbm mode. This is faster, but only allows strings for keys and values.
    :raises ValueError: Flag argument incorrect.
    """

    filename = _add_file_identifier(filename)

    if flag == "r":
        return _SaveStateReadOnly(filename, verify_checksums=verify_checksums, dbm_mode=dbm_mode)
    elif flag == "w":
        return _SaveStateReadWrite(filename, verify_checksums=verify_checksums, compact=compact, dbm_mode=dbm_mode)
    elif flag == "c":
        return _SaveStateCreate(filename, verify_checksums=verify_checksums, compact=compact, dbm_mode=dbm_mode)
    elif flag == "n":
        return _SaveStateNew(filename, verify_checksums=verify_checksums, compact=compact, dbm_mode=dbm_mode)
    else:
        raise ValueError("Flag argument must be 'r', 'c', 'w', or 'n'")
