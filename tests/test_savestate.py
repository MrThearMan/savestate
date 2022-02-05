import os
import pickle
import re
import struct
from argparse import Namespace

import pytest

import savestate

from .conftest import SAVESTATE_DIR, SAVESTATE_FILE, clear_savestate_dir, truncate_data_file


def test_file_identifier_gets_added(savestate_db):
    assert savestate_db.filename.endswith("savestate")


def test_flags():
    clear_savestate_dir()

    # Improper flag
    with pytest.raises(ValueError):
        savestate.open(SAVESTATE_FILE, flag="foo")

    # Test, that file can't be created on these modes.
    with pytest.raises(savestate.SaveStateError):
        savestate.open(SAVESTATE_FILE, flag="r")

    with pytest.raises(savestate.SaveStateError):
        savestate.open(SAVESTATE_FILE, flag="w")

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        db["foo"] = "bar"
        assert "bar" == db["foo"]

    # Test read only mode
    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:

        # All methods that read-only does should not have
        assert not hasattr(db, "__setitem__")
        assert not hasattr(db, "__delitem__")
        assert not hasattr(db, "sync")
        assert not hasattr(db, "compact")
        assert not hasattr(db, "clear")
        assert not hasattr(db, "setdefault")
        assert not hasattr(db, "pop")
        assert not hasattr(db, "popitem")
        assert not hasattr(db, "copy")
        assert not hasattr(db, "update")
        assert not hasattr(db, "_rename")
        assert not hasattr(db, "_write_headers")

        # Reading is fine
        assert "bar" == db["foo"]

    # Test read-write mode
    with savestate.open(filename=SAVESTATE_FILE, flag="w") as db:
        db["foo"] = "baz"
        assert "baz" == db["foo"]

    # Test create new always mode
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        assert "foo" not in db
        db["foo"] = "bar"
        assert "bar" == db["foo"]

    clear_savestate_dir()

    try:
        savestate.open(filename=SAVESTATE_FILE, flag="n")
    except savestate.SaveStateError:
        pytest.pytest.fail(
            "Opening SaveState with flag 'n' when file does not exist should not raise a 'SaveStateError'!"
        )


# --- Test setting and getting different types ---------------------------


def test_bytes(savestate_db):
    savestate_db[b"foo"] = b"bar"
    assert b"bar" == savestate_db[b"foo"]
    assert "bar" != savestate_db[b"foo"]
    del savestate_db[b"foo"]
    assert b"foo" not in savestate_db


def test_str(savestate_db):
    savestate_db["foo"] = "bar"
    assert "bar" == savestate_db["foo"]
    assert b"bar" != savestate_db["foo"]
    del savestate_db["foo"]
    assert "foo" not in savestate_db


def test_int(savestate_db):
    savestate_db[1] = 2
    assert 2 == savestate_db[1]
    del savestate_db[1]
    assert 1 not in savestate_db


def test_float(savestate_db):
    savestate_db[0.1] = 0.2
    assert 0.2 == savestate_db[0.1]
    del savestate_db[0.1]
    assert 0.1 not in savestate_db


def test_object(savestate_db):
    savestate_db[Namespace(a=b"gsdfff", b=None, c=True)] = Namespace(x=1, y=0x001, z="None")
    assert Namespace(x=1, y=0x001, z="None") == savestate_db[Namespace(a=b"gsdfff", b=None, c=True)]
    del savestate_db[Namespace(a=b"gsdfff", b=None, c=True)]
    assert Namespace(a=b"gsdfff", b=None, c=True) not in savestate_db


# --- Test usecase scenarios ---------------------------------------------


def test_close_and_reopen():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        assert "bar" == db["foo"]


def test_get_set_multiple(savestate_db):
    savestate_db["one"] = 1
    assert 1 == savestate_db["one"]
    savestate_db["two"] = 2
    assert 2 == savestate_db["two"]
    savestate_db["three"] = 3
    assert 1 == savestate_db["one"]
    assert 2 == savestate_db["two"]
    assert 3 == savestate_db["three"]


def test_keyerror_raised_when_key_does_not_exist(savestate_db):
    with pytest.raises(KeyError):
        x = savestate_db["foo"]

    with pytest.raises(KeyError):
        del savestate_db["foo"]

    with pytest.raises(KeyError):
        savestate_db.pop("foo")

    with pytest.raises(KeyError):
        savestate_db.popitem()


def test_updates(savestate_db):
    savestate_db["one"] = "foo"
    savestate_db["one"] = "bar"
    assert "bar" == savestate_db["one"]
    savestate_db["one"] = "baz"
    assert "baz" == savestate_db["one"]


def test_updates_persist():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "foo"
        db["one"] = "bar"
        db["one"] = "baz"

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        assert db["one"] == "baz"


def test_deletes(savestate_db):
    savestate_db["foo"] = "bar"
    del savestate_db["foo"]
    assert "foo" not in savestate_db


def test_deleted_key_not_there_when_reopened():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = 1
        db["two"] = 2
        del db["two"]

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        assert db["one"] == 1
        assert "two" not in db


def test_multiple_deletes():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "foo"
        del db["foo"]
        db["foo"] = "foo"
        del db["foo"]
        db["foo"] = "foo"
        del db["foo"]
        db["bar"] = "bar"

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        assert "foo" not in db
        assert db["bar"] == "bar"


def test_update_after_delete(savestate_db):
    savestate_db["one"] = 1
    del savestate_db["one"]
    savestate_db["two"] = 2
    savestate_db["one"] = 3

    assert savestate_db["two"] == 2
    assert savestate_db["one"] == 3


# --- Test savestate methods --------------------------------------------------


def test_get_method(savestate_db):
    savestate_db["foo"] = "bar"
    assert savestate_db["foo"] == savestate_db.get("foo")


def test_keys_method(savestate_db):
    savestate_db["one"] = 1
    savestate_db["two"] = 2
    savestate_db["three"] = 3
    assert savestate_db.keys() == ["one", "two", "three"]


def test_values_method(savestate_db):
    savestate_db["one"] = 1
    savestate_db["two"] = 2
    savestate_db["three"] = 3
    assert savestate_db.values() == [1, 2, 3]


def test_items_method(savestate_db):
    savestate_db["one"] = 1
    savestate_db["two"] = 2
    savestate_db["three"] = 3
    assert savestate_db.items() == [("one", 1), ("two", 2), ("three", 3)]


def test_close_method():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"

    assert not hasattr(db, "_data_file_descriptor")
    with pytest.raises(AttributeError):
        x = db["foo"]


def test_sync_method():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"
        db.sync()

    with pytest.raises(AttributeError):
        db.sync()


def test_contains_method(savestate_db):
    savestate_db["foo"] = "bar"
    assert "foo" in savestate_db


def test_iter_method(savestate_db):
    savestate_db["one"] = 1
    savestate_db["two"] = 2
    savestate_db["three"] = 3
    assert list(iter(savestate_db)) == ["one", "two", "three"]


def test_reversed_method(savestate_db):
    savestate_db["one"] = 1
    savestate_db["two"] = 2
    savestate_db["three"] = 3
    assert list(reversed(savestate_db)) == ["three", "two", "one"]


def test_len_method(savestate_db):
    savestate_db["one"] = "foo"
    savestate_db["one"] = "bar"
    savestate_db["two"] = "baz"
    assert len(savestate_db) == 2


def test_del_method(savestate_db):
    try:
        del savestate_db
        savestate_db = savestate.open(filename=SAVESTATE_FILE, flag="r")
    except:  # noqa
        pytest.fail("Database did not close gracefully when deleted")

    try:
        savestate_db = savestate.open(filename=SAVESTATE_DIR / "testcopy", flag="n")
        savestate_db = savestate.open(filename=SAVESTATE_FILE, flag="r")
    except:  # noqa
        pytest.fail("Database did not close gracefully when garbage collected")


def test_context_manager():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = 1
        db["two"] = 2
        db["three"] = 3

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        assert 1 == db["one"]
        assert 2 == db["two"]
        assert 3 == db["three"]


def test_pop_method(savestate_db):
    savestate_db["foo"] = "bar"
    value = savestate_db.pop("foo")
    assert value == "bar"

    with pytest.raises(KeyError):
        savestate_db.pop("bar")

    value = savestate_db.pop("bar", None)
    assert value is None
    assert "one" not in savestate_db


def test_popitem_method(savestate_db):
    savestate_db["one"] = 1
    savestate_db["two"] = 2
    key, value = savestate_db.popitem()
    assert 1 == savestate_db["one"]
    assert key == "two"
    assert value == 2
    assert "two" not in savestate_db


def test_clear_method():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"
        db["three"] = "bar"

    before = os.path.getsize(db.filepath)

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        db.clear()

        with pytest.raises(KeyError):
            x = db["one"]

        with pytest.raises(KeyError):
            x = db["two"]

        with pytest.raises(KeyError):
            x = db["three"]

    # Clearing should compact the database
    after = os.path.getsize(db.filepath)
    assert after < before


def test_setdefault_method(savestate_db):
    savestate_db["foo"] = "bar"
    value = savestate_db.setdefault("foo", "baz")
    assert value == "bar"
    try:
        value = savestate_db.setdefault("one", 1)
        assert value == 1
    except KeyError:
        pytest.fail("Setdefault should not raise KeyError.")


def test_update_method(savestate_db):
    savestate_db.update({"foo": "bar", "one": 1}, two=2, foo="baz")
    assert savestate_db["foo"] == "baz"
    assert savestate_db["one"] == 1
    assert savestate_db["two"] == 2


def test_copy_method():
    copyfile = SAVESTATE_DIR / "testcopy"

    for mode in ("n", "w", "c"):
        with savestate.open(filename=SAVESTATE_FILE, flag=mode) as db:
            db["foo"] = "bar"
            new_db = db.copy(copyfile)
            try:
                assert db["foo"] == new_db["foo"]
                assert type(db) == type(new_db)
            finally:
                new_db.close()
                os.remove(new_db.filepath)

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        assert not hasattr(db, "copy")


def test_covert_to_bytes(savestate_db):
    assert savestate_db._convert_to_bytes("foo") == pickle.dumps("foo", protocol=5)


def test_covert_from_bytes(savestate_db):
    value = pickle.dumps("foo", protocol=5)
    assert savestate_db._convert_from_bytes(value) == pickle.loads(value)


def test_verify_checksums():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"

    with savestate.open(SAVESTATE_FILE, flag="r", verify_checksums=True) as db:
        try:
            _ = db["foo"]
        except savestate.SaveStateChecksumError:
            pytest.fail("Checksum failed.")


# --- Test compaction ----------------------------------------------------


def test_compact():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        for i in range(10):
            db[i] = i
        for i in range(5):
            del db[i]

    before = os.path.getsize(db.filepath)

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        db.compact()

    after = os.path.getsize(db.filepath)
    assert after < before


def test_compact_does_not_leave_behind_files():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        before = len(os.listdir(SAVESTATE_DIR))
        for i in range(10):
            db[i] = i
        for i in range(10):
            del db[i]

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        db.compact()

    after = len(os.listdir(SAVESTATE_DIR))
    assert before == after


def test_compact_on_close():
    db = savestate.open(filename=SAVESTATE_FILE, flag="n")
    try:
        db["foo"] = "bar"
        del db["foo"]
    finally:
        db.close(compact=True)

    with savestate.open(filename=SAVESTATE_FILE, flag="r") as db:
        # Only header in the file.
        assert db._current_offset == 13


def test_compact_set_and_get(savestate_db):
    for i in range(10):
        savestate_db[i] = i
    for i in range(5):
        del savestate_db[i]
    for i in range(5, 10):
        savestate_db[i] = "foo"

    savestate_db.compact()

    for i in range(5, 10):
        assert savestate_db[i] == "foo"

    assert len(savestate_db) == 5

    for i in range(5):
        savestate_db[i] = i

    assert len(savestate_db) == 10


# --- Test corrupted data ------------------------------------------------


def test_bad_file_identifier_raises_error():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"

    with open(db.filepath, "r+b") as f:
        data = f.read()

    assert data[:9] == b"savestate"

    with open(db.filepath, "r+b") as f:
        f.seek(0)
        f.write(b"fdjkasdtj")

    with pytest.raises(savestate.SaveStateLoadError, match="File is not a SaveState file."):
        savestate.open(filename=SAVESTATE_FILE, flag="c")


def test_incompatible_version_number_raises_error():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"

    with open(db.filepath, "r+b") as f:
        f.seek(9)
        f.write(struct.pack("!H", 9))

    match = re.escape("Incompatible file version (got: v9, can handle: v1)")
    with pytest.raises(savestate.SaveStateLoadError, match=match):
        savestate.open(filename=SAVESTATE_FILE, flag="c")


def test_incompatible_picking_version_raises_error():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["foo"] = "bar"

    with open(db.filepath, "r+b") as f:
        f.seek(11)
        f.write(struct.pack("!H", 1))

    match = re.escape("Incompatible pickling protocol. (got: v1, requires: v5)")
    with pytest.raises(savestate.SaveStateLoadError, match=match):
        savestate.open(filename=SAVESTATE_FILE, flag="c")


def test_warns_but_recovers_from_bad_key_value_size_indicator():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"
        db["three"] = "bar"

    before = os.path.getsize(db.filepath)

    # Write garbage as the key and value indicator for the second key.
    # The first key should still be read, and the savestate_db formed from that.
    with open(db.filepath, "r+b") as f:
        f.seek(13 + 8 + 18 + 18 + 4)
        f.write(b"\x00" * 8)

    match = re.escape("Zero key size at position 61/159. Could not continue to read data.")
    with pytest.warns(BytesWarning, match=match):
        db = savestate.open(filename=SAVESTATE_FILE, flag="c")

    try:
        assert db["one"] == "bar"

        with pytest.raises(KeyError):
            x = db["two"]

        with pytest.raises(KeyError):
            x = db["three"]

    finally:
        # Test, that compaction removes the corrupted data.
        db.close(compact=True)

    after = os.path.getsize(db.filepath)
    assert after < before

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        assert db["one"] == "bar"


def test_warns_but_recovers_from_bad_key_data():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"
        db["three"] = "bar"

    before = os.path.getsize(db.filepath)

    # Write garbage to the beginning of the second key data.
    # The first and third key should still be read, and the savestate formed from that.
    with open(db.filepath, "r+b") as f:
        f.seek(13 + 8 + 18 + 18 + 4 + 8)
        f.write(b"\x00" * 8)

    match = re.escape("Data was corrupted at position 87/159. Compaction necessary.")
    with pytest.warns(BytesWarning, match=match):
        db = savestate.open(filename=SAVESTATE_FILE, flag="c")

    try:
        assert db["one"] == "bar"

        with pytest.raises(KeyError):
            x = db["two"]

        assert db["three"] == "bar"
    finally:
        # Test, that compaction removes the corrupted data.
        db.close(compact=True)

    after = os.path.getsize(db.filepath)
    assert after < before

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        assert db["one"] == "bar"
        assert db["three"] == "bar"


def test_warns_but_recovers_from_bad_value_data():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"
        db["three"] = "bar"

    before = os.path.getsize(db.filepath)

    # # Write garbage to the beginning of the second value data.
    # The first and third key should still be read, and the savestate_db formed from that.
    with open(db.filepath, "r+b") as f:
        f.seek(13 + 8 + 18 + 18 + 4 + 8 + 18)
        f.write(b"\x00" * 8)

    match = re.escape("Data was corrupted at position 87/159. Compaction necessary.")
    with pytest.warns(BytesWarning, match=match):
        db = savestate.open(filename=SAVESTATE_FILE, flag="c")

    try:
        assert db["one"] == "bar"

        with pytest.raises(KeyError):
            x = db["two"]

        assert db["three"] == "bar"

    finally:
        # Test, that compaction removes the corrupted data.
        db.close(compact=True)

    after = os.path.getsize(db.filepath)
    assert after < before

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        assert db["one"] == "bar"
        assert db["three"] == "bar"


def test_warns_but_recovers_from_bad_checksum():
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"
        db["three"] = "bar"

    before = os.path.getsize(db.filepath)

    # # Write garbage to the beginning of the second value data.
    # The first and third key should still be read, and the savestate_db formed from that.
    with open(db.filepath, "r+b") as f:
        f.seek(13 + 8 + 18 + 18 + 4 + 8 + 18 + 18)
        f.write(b"\x00" * 4)

    match = re.escape("Data was corrupted at position 87/159. Compaction necessary.")
    with pytest.warns(BytesWarning, match=match):
        db = savestate.open(filename=SAVESTATE_FILE, flag="c")

    try:
        assert db["one"] == "bar"

        with pytest.raises(KeyError):
            x = db["two"]

        assert db["three"] == "bar"
    finally:
        # Test, that compaction removes the corrupted data.
        db.close(compact=True)

    after = os.path.getsize(db.filepath)
    assert after < before

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        assert db["one"] == "bar"
        assert db["three"] == "bar"


def test_warns_but_recovers_from_missing_data_at_the_end_of_the_file():
    # e.g. computer crashes when writing large amounts of data
    # so parts of it were not written.
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"
        db["three"] = "bar"

    before = os.path.getsize(db.filepath)

    truncate_data_file(filepath=db.filepath, bytes_from_end=8)

    match = re.escape("Some data is missing at the end of the file. Compaction necessary.")
    with pytest.warns(BytesWarning, match=match):
        db = savestate.open(filename=SAVESTATE_FILE, flag="c")

    try:
        assert db["one"] == "bar"
        assert db["two"] == "bar"

        with pytest.raises(KeyError):
            x = db["three"]

    finally:
        # Test, that compaction removes the corrupted data.
        db.close(compact=True)

    after = os.path.getsize(db.filepath)
    assert after + 8 < before

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        assert db["one"] == "bar"


def test_warns_but_recovers_from_trying_to_read_past_the_end_of_the_file():

    with savestate.open(filename=SAVESTATE_FILE, flag="n") as db:
        db["one"] = "bar"
        db["two"] = "bar"

    before = os.path.getsize(db.filepath)

    # Set value length indicator to 255 instead of 18
    with open(db.filepath, "r+b") as f:
        f.seek(13 + 8 + 18 + 18 + 4 + 4)
        f.write(b"\x00\x00\x00\xff")

    match = re.escape("Some data is missing at the end of the file. Compaction necessary.")
    with pytest.warns(BytesWarning, match=match):
        db = savestate.open(filename=SAVESTATE_FILE, flag="c")

    try:
        assert db["one"] == "bar"

        with pytest.raises(KeyError):
            x = db["two"]

    finally:
        # Test, that compaction removes the corrupted data.
        db.close(compact=True)

    after = os.path.getsize(db.filepath)
    assert after + 8 < before

    with savestate.open(filename=SAVESTATE_FILE, flag="c") as db:
        assert db["one"] == "bar"
