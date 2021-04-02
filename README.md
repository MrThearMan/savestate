## SaveState - persistent storage of arbitrary python objects

SaveState is meant to be a cross-platform fast file storage for arbitrary python objects, like python's [shelve](https://docs.python.org/3/library/shelve.html) module.
It is mostly a rewrite of [semidbm2](https://github.com/quora/semidbm2), but with more mapping-like functions, a context manager, and the aforementioned support for arbitrary python objects.

### Implementation details:
- Pure python
- No requirements or dependencies
- A dict-like interface (no unions)
- Same, single file on windows and linux (unlike shelve)
- Key and value integrity can be evaluated with a checksum, which will detect data corruption on key access.
- Recovery from missing bytes at the end of the file, or small amounts of corrupted data in the middle
- Both values AND keys put in savestate must support [pickling](https://docs.python.org/3/library/pickle.html#module-pickle).
Note the [security implications](https://docs.python.org/3/library/pickle.html#module-pickle) of this!
  - This means that you can use arbitrary objects as keys if they support pickle (unlike shelve)
- All the keys of the savestate are kept in memory, which limits the savestate size (not a problem for most applications)
- NOT Thread safe, so cannot be accessed by multiple processes
- File is append-only, so the more non-read operations you do, the more the file size is going to balloon
  - However, you can *compact* the savestate, usually on *savestate.close()*, which will replace the savestate with a new file with only the current non-deleted data.
  This will impact performance a little, but not by much
  
### Performance:
- About 50-60% of the performance of shelve with [gdbm](https://docs.python.org/3/library/dbm.html#module-dbm.gnu) (linux), 
  but >5000% compared to shelve with [dumbdbm](https://docs.python.org/3/library/dbm.html#module-dbm.dumb) (windows) (>20000% for deletes!)
  - Performance is more favorable with large keys and values when compared to gdbm, 
    but gdbm is still faster on subsequent reads/writes thanks to its caching
- A dbm-mode for about double the speed of regular mode, but only string-type keys and values
  - This is about 25-30% of the performance of gdbm on its own.
  - Note: Values will be returned in bytes form!
  
> Source code includes a benchmark that you can run to get more accurate performance on your specific machine.

## Using SaveState:

#### Use with open and close:
```python
>>> import savestate
>>> 
>>> # Open savestate
>>> state = savestate.open("savestate", "c")
>>> 
>>> # Add data to savestate
>>> state["foo"] = "bar"
>>> 
>>> # Get data from savestate
>>> print(state["foo"])
bar

>>> # Delete data from savestate
>>> del state["foo"]
>>> 
>>> # Close the savestate
>>> state.close()
```

#### Use as a context manager:

```python
>>> with savestate.open("filename.savestate", "c") as state:   
>>>     state["foo"] = "baz"                                                   
>>>     ...
```

## Documentation:

##### *savestate.open(filename, flag="r", verify_checksums=False, compact=False, dbm_mode=False)*
* **filename**: str - The name of the savestate. Will have the '.savestate' file extension added to it if it doesn't have it.
* **flag**: Literal["r", "w", "c", "n"] - Specifies how the savestate should be opened.
  * "r" = Open existing savestate for reading only *(default)*.
  * "w" = Open existing savestate for reading and writing.
  * "c" = Open savestate for reading and writing, creating it if it does not exist.
  * "n" = Always create a new, empty savestate, open for reading and writing.
* **verify_checksum**: bool - Verify that the checksum for a key and value pair is correct on every *\_\_getitem\_\_* call
* **compact**: bool - Indicate whether to compact the savestate before closing it. No effect in read only mode.
* **dbm_mode**: bool - Operate in dbm mode. This is faster, but only allows strings for keys and values.


#### 'Read-Only' mode:

```python
>>> # Magic methods
>>> savestate[key]
>>> key in savestate
>>> len(savestate)
>>> iter(savestate)
>>> reversed(savestate)
>>> str(savestate)
>>> repr(savestate)
>>>
>>> # Properties
>>> savestate.filepath  # absolute path (& filename)
>>> savestate.filename  # filename (& extension)
>>> savestate.isopen
>>>
>>> # Mapping-like methods
>>> savestate.keys()
>>> savestate.values()
>>> savestate.items()
>>> savestate.get(key: Any, default: Any = None)
>>>
>>> # Special methods
>>> savestate.close()
>>> ### Closes the savestate. Accessing keys after this 
>>> ### will cause an AttributeError.
```

#### 'Read-Write', 'Create' and 'New' modes:
- Extend read-only mode with these methods

```python
>>> # Magic methods
>>> savestate[key] = value
>>> del savestate[key]
>>> 
>>> # Mapping-like methods
>>> savestate.pop(key: Any, default: Any = None)
>>> savestate.popitem()
>>> savestate.clear()
>>> savestate.setdefault(key: Any, default: Any = None)
>>> savestate.update(other: Mapping[Any, Any], **kwargs: Any)
>>> savestate.copy(new_filename: str)
>>> ### AssertionError if new filename is same as current one.
>>> ### THIS WILL OVERWRITE ANY FILES WITH THE GIVEN FILENAME!
>>> ### Note: new filename will have '.savestate' added to it, 
>>> ### if it doesn't have it
>>>
>>> # Special methods
>>> savestate.sync()
>>> ### Flushes existing data buffers and ensures that data
>>> ### is written to the disk. Always called on savestate.close()
>>> savestate.compact()
>>> ### Rewrite the contents of the files, which will
>>> ### reduce the size of the file due to implementation details
>>> savestate.close(compact: bool = False)
>>> ### Setting compact=True will compact the savestate
>>> ### even if it was not set so at savestate.open()
```
