# Basic usage

## Use with open and close:
```python
import savestate

# Open savestate
state = savestate.open("savestate", "c")

# Add data to savestate
state["foo"] = "bar"

# Get data from savestate
state["foo"]   # -> bar

# Delete data from savestate
del state["foo"]

# Close the savestate
state.close()
```

## Use as a context manager:

```python
with savestate.open("filename.savestate", "c") as state:  
    state["foo"] = "baz"  
    ...
```