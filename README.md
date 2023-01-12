# SaveState

[![Coverage Status][coverage-badge]][coverage]
[![GitHub Workflow Status][status-badge]][status]
[![PyPI][pypi-badge]][pypi]
[![GitHub][licence-badge]][licence]
[![GitHub Last Commit][repo-badge]][repo]
[![GitHub Issues][issues-badge]][issues]
[![Python Version][version-badge]][pypi]

```shell
pip install savestate
```

---

**Documentation**: [https://mrthearman.github.io/savestate/](https://mrthearman.github.io/savestate/)

**Source Code**: [https://github.com/MrThearMan/savestate/](https://github.com/MrThearMan/savestate/)

---

SaveState is a cross-platform fast file storage for arbitrary python objects.
It's similar to python's builtin [shelve][shelve] module, but aims to be more
performant on Windows while being cross-platform compatible.

Savestate is inspired by [semidbm2][semidbm2], with a more modern interface.
mapping-like functions, a context manager, and support for
arbitrary python objects.

### Implementation details:
- Pure python
- No requirements or dependencies
- A dict-like interface (no unions)
- Same, single file on Windows and Linux (unlike shelve)
- Key and value integrity can be evaluated with a checksum, which will detect data corruption on key access.
- Recovery from missing bytes at the end of the file, or small amounts of corrupted data in the middle
- Both values AND keys put in savestate must support [pickling][pickling].
Note the [security implications][security] of this!
  - This means that you can use arbitrary objects as keys if they support pickle (unlike shelve)
- All the keys of the savestate are kept in memory, which limits the savestate size (not a problem for most applications)
- NOT Thread safe, so cannot be accessed by multiple processes
- File is append-only, so the more non-read operations you do, the more the file size is going to balloon
  - However, you can *compact* the savestate, usually on *savestate.close()*, which will replace the savestate with a new file with only the current non-deleted data.
  This will impact performance a little, but not by much

### Performance:
- About 50-60% of the performance of shelve with [gdbm][gdbm] (linux),
  but >5000% compared to shelve with [dumbdbm][dumbdbm] (windows) (>20000% for deletes!)
  - Performance is more favorable with large keys and values when compared to gdbm,
    but gdbm is still faster on subsequent reads/writes thanks to its caching
- A dbm-mode for about double the speed of regular mode, but only string-type keys and values
  - This is about 25-30% of the performance of gdbm on its own.
  - Note: Values will be returned in bytes form!

> Source code includes a benchmark that you can run to get more accurate performance on your specific machine.


[shelve]: https://docs.python.org/3/library/shelve.html
[semidbm2]: https://github.com/quora/semidbm2
[pickling]: https://docs.python.org/3/library/pickle.html#module-pickle
[security]: https://docs.python.org/3/library/pickle.html#module-pickle
[gdbm]: https://docs.python.org/3/library/dbm.html#module-dbm.gnu
[dumbdbm]: https://docs.python.org/3/library/dbm.html#module-dbm.dumb

[coverage-badge]: https://coveralls.io/repos/github/MrThearMan/savestate/badge.svg?branch=main
[status-badge]: https://img.shields.io/github/actions/workflow/status/MrThearMan/savestate/test.yml?branch=main
[pypi-badge]: https://img.shields.io/pypi/v/savestate
[licence-badge]: https://img.shields.io/github/license/MrThearMan/savestate
[repo-badge]: https://img.shields.io/github/last-commit/MrThearMan/savestate
[issues-badge]: https://img.shields.io/github/issues-raw/MrThearMan/savestate
[version-badge]: https://img.shields.io/pypi/pyversions/savestate

[coverage]: https://coveralls.io/github/MrThearMan/savestate?branch=main
[status]: https://github.com/MrThearMan/savestate/actions/workflows/test.yml
[pypi]: https://pypi.org/project/savestate
[licence]: https://github.com/MrThearMan/savestate/blob/main/LICENSE
[repo]: https://github.com/MrThearMan/savestate/commits/main
[issues]: https://github.com/MrThearMan/savestate/issues
