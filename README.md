## quickshelve - persistent storage of arbitrary python objects

Similarly to python's [shelve](https://docs.python.org/3/library/shelve.html)-module, allows persistent storage of python objects, if they support [pickling](https://docs.python.org/3/library/pickle.html#module-pickle).

### Pros:
- 

### Cons:
- 


#### Use with open and close:
```
import dbmw

# Open database

db = dbmw.open("database", "c")

db["foo"] = "bar"
db["foo"]
>>> "bar"

"foo" in db
>>> True

del db["foo"]
"foo" in db
>>> False

db.close(compact=True)    # Rewrites the db to save space.
# db.close()              # Compaction is off by default.
```

#### Use as a contect manager:

```
with dbmw.open("database", "c"):   
    db["foo"] = "baz"                                                   
    ...
```

#### Settings:

```open(..., flag="r", ...)``` | Open in 'read-only' mode (default). Raises DBMWError if file does not exist.

```open(..., flag="w", ...)``` | Open in 'read-write' mode. Raises DBMWError if file does not exist.

```open(..., flag="c", ...)``` | Open in 'create' mode. Creates new file if it does not exist.

```open(..., flag="n", ...)``` | Open in 'new' mode. Creates new file, even if the file exists.

```open(..., verify_checksum=True, ...)``` | Verify key and value integrity on each key access

```open(..., compact=True, ...)``` | Set compaction from open.
