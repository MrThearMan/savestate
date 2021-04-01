## SaveState - persistent storage of arbitrary python objects

SaveState is meant to be a cross-platform fast file storage for arbitrary python objects, similarly to python's [shelve](https://docs.python.org/3/library/shelve.html)-module.
It's mostly a rewrite of [semidbm2](https://github.com/quora/semidbm2), but with more mapping-like functions, a context manager, and the aforementioned support for arbitrary python objects.

### Implementation details:
- No requirements or dependencies
- A dict-like interface (no unions)
- Same, single file on windows and linux (unlike shelve)
- Key and value integrity can be evaluated with a checksum, which will detect data corruption on key access.
  - This is also used to recover from data corruption by skipping data which can't be validated
- Objects have to support [pickling](https://docs.python.org/3/library/pickle.html#module-pickle) so that they can be used with savestate.
Note the [security implications](https://docs.python.org/3/library/pickle.html#module-pickle) of this!
- All the keys of the savestate are kept in memory, which limits the savestate size (not a problem for most applications)
- NOT Thread safe, so can't be accessed by multiple processes
- File is append-only, so the more non-read operations you do, the more the filesize is going to balloon
  - Howevever, you can *compact* the savestate, usually on *savestate.close()*, which will replace the savestate with a new file with only the current non-deleted data.
  This will impact performance a little, but not by much
  
### Performance:
- About 50-60% of the performance of shelve with [gdbm](https://docs.python.org/3/library/dbm.html#module-dbm.gnu) (linux), 
  but >5000% compared to shelve with [dumbdbm](https://docs.python.org/3/library/dbm.html#module-dbm.dumb) (windows) (>20000% for deletes!)
  - Performance is more favourable with large keys and values when compared to [gdbm](https://docs.python.org/3/library/dbm.html#module-dbm.gnu), 
    but gdbm's still faster on subsequent reads/writes thanks to it's caching
- A dbm-mode for about double the speed of reqular mode, but only string-type keys and value
  - This is about 25-30% of the performance of [gdbm](https://docs.python.org/3/library/dbm.html#module-dbm.gnu) on its own.
  
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
>>> # Get item from savestate
>>> print(state["foo"])
bar

>>> # Delete key from savestate
>>> del state["foo"]
>>> 
>>> # Close the savestate
>>> state.close()
```

#### Use as a contect manager:

```python
>>> with savestate.open("filename.savestate", "c") as state:   
>>>     state["foo"] = "baz"                                                   
>>>     ...
```

## Documentation:

##### *savestate.open(filename, flag, verify_checksums, compact, dbm_mode)*
* **filename**: str - The name of the savestate. Will have .savestate added to it, if it doesn't have it.
* **flag**: Literal["r", "w", "c", "n"] - Specifies how the savestate should be opened.
  * "r" = Open existing savestate for reading only *(default)*.
  * "w" = Open existing savestate for reading and writing.
  * "c" = Open savestate for reading and writing, creating it if it doesn't exist.
  * "n" = Always create a new, empty savestate, open for reading and writing.
* **verify_checksum**: bool - Verify that the checksums for each value are correct on every *\_\_getitem\_\_* call
* **compact**: bool - Indicate whether or not to compact the savestate before closing it. No effect in read only mode.
* **dbm_mode**: bool -  Operate in dbm mode. This is faster, but only allows strings for keys and values.


#### 'Read-Only' mode:

```python
>>>  # Magic methods
>>> savestate[key]
>>> key in savestate
>>> len(savestate)
>>> iter(savestate)
>>> reversed(savestate)
>>> str(savestate)
>>> repr(savestate)
>>>
>>>  # Properties
>>> savestate.filepath
>>> savestate.filename
>>> savestate.isopen
>>>
>>>  # Mapping-like methods
>>> savestate.keys()
>>> savestate.values()
>>> savestate.items()
>>> savestate.get(key: Any, default: Any = None)
>>>
>>>  # Special methods
>>> savestate.close()
>>>  ### Closes the savestate. Accessing keys after this 
>>>  ### will cause an AttributeError.
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
>>> savestate.popitem() -> tuple[Any, Any]
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
>>> ### Flushes existing databuffers and ensures that data
>>> ### is written to the disk. Always called on savestate.close()
>>> savestate.compact()
>>> ### Rewrite the contents of the files, which will
>>> ### reduce the size of the file due to implementation details
>>> savestate.close(compact: bool = False)
>>> ### Setting compact=True will compact the savestate
>>> ### even if it was not set so at savestate.open()
```
