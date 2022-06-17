# Documentation


#### savestate.open(...)

* **filename**: str - The name of the savestate. Will have the '.savestate' file extension added to it if it doesn't have it.
* **flag**: Literal["r", "w", "c", "n"] - Specifies how the savestate should be opened.
    * "r" = Open existing savestate for reading only *(default)*.
    * "w" = Open existing savestate for reading and writing.
    * "c" = Open savestate for reading and writing, creating it if it does not exist.
    * "n" = Always create a new, empty savestate, open for reading and writing.
* **verify_checksum**: bool - Verify that the checksum for a key and value pair is correct on every `__getitem__` call
* **compact**: bool - Indicate whether to compact the savestate before closing it. No effect in read only mode.
* **dbm_mode**: bool - Operate in dbm mode. This is faster, but only allows strings for keys and values.


#### 'Read-Only' mode

```python
# Magic methods
savestate[key]
key in savestate
len(savestate)
iter(savestate)
reversed(savestate)
str(savestate)
repr(savestate)

# Properties
savestate.filepath  # absolute path (& filename)
savestate.filename  # filename (& extension)
savestate.isopen

# Mapping-like methods
savestate.keys()
savestate.values()
savestate.items()
savestate.get(key: Any, default: Any = None)

# Special methods
savestate.close()
### Closes the savestate. Accessing keys after this
### will cause an AttributeError.
```

#### 'Read-Write', 'Create' and 'New' modes
- Extend read-only mode with these methods

```python
# Magic methods
savestate[key] = value
del savestate[key]

# Mapping-like methods
savestate.pop(key: Any, default: Any = None)
savestate.popitem()
savestate.clear()
savestate.setdefault(key: Any, default: Any = None)
savestate.update(other: Mapping[Any, Any], **kwargs: Any)
savestate.copy(new_filename: str)
### AssertionError if new filename is same as current one.
### THIS WILL OVERWRITE ANY FILES WITH THE GIVEN FILENAME!
### Note: new filename will have '.savestate' added to it,
### if it doesn't have it

# Special methods
savestate.sync()
### Flushes existing data buffers and ensures that data
### is written to the disk. Always called on savestate.close()
savestate.compact()
### Rewrite the contents of the files, which will
### reduce the size of the file due to implementation details
savestate.close(compact: bool = False)
### Setting compact=True will compact the savestate
### even if it was not set so at savestate.open()
```
