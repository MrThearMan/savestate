"""Unittests for DBMW."""

import os
import shutil
import pickle
import struct
import unittest
import dbmw
from argparse import Namespace


class TestDBMW(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = "testdir"
        cls.tempfile = "testfile"
        cls.filepath = os.path.join(cls.tempdir, cls.tempfile)

    @classmethod
    def tearDownClass(cls) -> None:
        if os.path.exists(cls.tempdir):  # noqa
            shutil.rmtree(cls.tempdir)  # noqa

    def setUp(self) -> None:
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

        os.mkdir(self.tempdir)
        self.db = dbmw.open(filename=self.filepath, flag="n")

    def tearDown(self) -> None:
        if self.db.is_open:
            self.db.close()

    def truncate_data_file(self, bytes_from_end: int) -> None:
        with open(self.db.filepath, "rb") as f:
            data = f.read()
        with open(self.db.filepath, "wb") as f:
            f.write(data[:-bytes_from_end])

    # --- Tests -------------------------------------------------------------

    def test_file_identifier_gets_added(self):
        self.assertEqual(self.db.filename[-5:], ".dbmw")

    def test_flags(self):
        self.db.close()
        shutil.rmtree(self.tempdir)
        os.mkdir(self.tempdir)

        # Improper flag
        self.assertRaises(ValueError,  dbmw.open, filename=self.filepath, flag="foo")

        # Test that file can't be created on these modes.
        self.assertRaises(dbmw.DBMError, dbmw.open, filename=self.filepath, flag="r")
        self.assertRaises(dbmw.DBMError, dbmw.open, filename=self.filepath, flag="w")

        try:
            self.db = dbmw.open(filename=self.filepath, flag="c")
        except dbmw.DBMError:
            self.fail("Opening DBMW with flag 'c' when file does not exist should not raise a 'DBMWError'!")

        self.db["foo"] = "bar"
        self.assertEqual("bar", self.db["foo"])
        self.db.close()

        # Test read only mode
        self.db = dbmw.open(filename=self.filepath, flag="r")
        # All methods that read-only does should not have
        self.assertFalse(hasattr(self.db, "__setitem__"))
        self.assertFalse(hasattr(self.db, "__delitem__"))
        self.assertFalse(hasattr(self.db, "sync"))
        self.assertFalse(hasattr(self.db, "compact"))
        self.assertFalse(hasattr(self.db, "clear"))
        self.assertFalse(hasattr(self.db, "setdefault"))
        self.assertFalse(hasattr(self.db, "pop"))
        self.assertFalse(hasattr(self.db, "popitem"))
        self.assertFalse(hasattr(self.db, "copy"))
        self.assertFalse(hasattr(self.db, "update"))
        self.assertFalse(hasattr(self.db, "_rename"))
        self.assertFalse(hasattr(self.db, "_write_headers"))
        # Reading is fine
        self.assertEqual("bar", self.db["foo"])
        self.db.close()

        # Test read-write mode
        self.db = dbmw.open(filename=self.filepath, flag="w")
        self.db["foo"] = "baz"
        self.assertEqual("baz", self.db["foo"])
        self.db.close()

        # Test create new always mode
        self.db = dbmw.open(filename=self.filepath, flag="n")
        self.assertTrue("foo" not in self.db)
        self.db["foo"] = "bar"
        self.assertEqual("bar", self.db["foo"])
        self.db.close()

        shutil.rmtree(self.tempdir)
        os.mkdir(self.tempdir)

        try:
            self.db = dbmw.open(filename=self.filepath, flag="n")
        except dbmw.DBMError:
            self.fail("Opening DBMW with flag 'n' when file does not exist should not raise a 'DBMWError'!")

    # --- Test setting and getting different types ---------------------------

    def test_bytes(self):
        self.db[b"foo"] = b"bar"
        self.assertEqual(b"bar", self.db[b"foo"])
        self.assertNotEqual("bar", self.db[b"foo"])
        del self.db[b"foo"]
        self.assertTrue(b"foo" not in self.db)

    def test_str(self):
        self.db["foo"] = "bar"
        self.assertEqual("bar", self.db["foo"])
        self.assertNotEqual(b"bar", self.db["foo"])
        del self.db["foo"]
        self.assertTrue("foo" not in self.db)

    def test_int(self):
        self.db[1] = 2
        self.assertEqual(2, self.db[1])
        del self.db[1]
        self.assertTrue(1 not in self.db)

    def test_float(self):
        self.db[0.1] = 0.2
        self.assertEqual(0.2, self.db[0.1])
        del self.db[0.1]
        self.assertTrue(0.1 not in self.db)

    def test_object(self):
        self.db[Namespace(a=b"gsdfff", b=None, c=True)] = Namespace(x=1, y=0x001, z="None")
        self.assertEqual(Namespace(x=1, y=0x001, z="None"), self.db[Namespace(a=b"gsdfff", b=None, c=True)])
        del self.db[Namespace(a=b"gsdfff", b=None, c=True)]
        self.assertTrue(Namespace(a=b"gsdfff", b=None, c=True) not in self.db)

    # --- Test usecase scenarios ---------------------------------------------

    def test_close_and_reopen(self):
        self.db["foo"] = "bar"
        self.db.close()
        self.db = dbmw.open(filename=self.filepath, flag="r")
        self.assertEqual("bar", self.db["foo"])

    def test_get_set_multiple(self):
        self.db["one"] = 1
        self.assertEqual(1, self.db["one"])
        self.db["two"] = 2
        self.assertEqual(2, self.db["two"])
        self.db["three"] = 3
        self.assertEqual(1, self.db["one"])
        self.assertEqual(2, self.db["two"])
        self.assertEqual(3, self.db["three"])

    def test_keyerror_raised_when_key_does_not_exist(self):
        self.assertRaises(KeyError, self.db.__getitem__, "foo")
        self.assertRaises(KeyError, self.db.__delitem__, "foo")
        self.assertRaises(KeyError, self.db.get, "foo")
        self.assertRaises(KeyError, self.db.pop, "foo")
        self.assertRaises(KeyError, self.db.popitem)

    def test_updates(self):
        self.db["one"] = "foo"
        self.db["one"] = "bar"
        self.assertEqual("bar", self.db["one"])
        self.db["one"] = "baz"
        self.assertEqual("baz", self.db["one"])

    def test_updates_persist(self):
        self.db["one"] = "foo"
        self.db["one"] = "bar"
        self.db["one"] = "baz"
        self.db.close()
        self.db = dbmw.open(filename=self.filepath, flag="r")
        self.assertEqual(self.db["one"], "baz")

    def test_deletes(self):
        self.db["foo"] = "bar"
        del self.db["foo"]
        self.assertTrue("foo" not in self.db)

    def test_deleted_key_not_there_when_reopened(self):
        self.db["one"] = 1
        self.db["two"] = 2
        del self.db["two"]
        self.db.close()

        self.db = dbmw.open(filename=self.filepath, flag="r")
        self.assertEqual(self.db["one"], 1)
        self.assertTrue("two" not in self.db)

    def test_multiple_deletes(self):
        self.db["foo"] = "foo"
        del self.db["foo"]
        self.db["foo"] = "foo"
        del self.db["foo"]
        self.db["foo"] = "foo"
        del self.db["foo"]
        self.db["bar"] = "bar"
        self.db.close()

        self.db = dbmw.open(filename=self.filepath, flag="r")
        self.assertTrue("foo" not in self.db)
        self.assertEqual(self.db["bar"], "bar")

    def test_update_after_delete(self):
        self.db["one"] = 1
        del self.db["one"]
        self.db["two"] = 2
        self.db["one"] = 3

        self.assertEqual(self.db["two"], 2)
        self.assertEqual(self.db["one"], 3)

    # --- Test dbmw methods --------------------------------------------------

    def test_get_method(self):
        self.db["foo"] = "bar"
        self.assertEqual(self.db["foo"], self.db.get("foo"))

    def test_keys_method(self):
        self.db["one"] = 1
        self.db["two"] = 2
        self.db["three"] = 3
        self.assertEqual(self.db.keys(), ["one", "two", "three"])

    def test_values_method(self):
        self.db["one"] = 1
        self.db["two"] = 2
        self.db["three"] = 3
        self.assertEqual(self.db.values(), [1, 2, 3])

    def test_items_method(self):
        self.db["one"] = 1
        self.db["two"] = 2
        self.db["three"] = 3
        self.assertEqual(self.db.items(), [("one", 1), ("two", 2), ("three", 3)])

    def test_close_method(self):
        self.db["foo"] = "bar"
        self.db.close()
        self.assertFalse(hasattr(self.db, "_data_file_descriptor"))
        self.assertRaises(AttributeError, self.db.__getitem__, "foo")

    def test_sync_method(self):
        self.db["foo"] = "bar"
        self.db.sync()
        self.db.close()
        self.assertRaises(AttributeError, self.db.sync)

    def test_contains_method(self):
        self.db["foo"] = "bar"
        self.assertTrue("foo" in self.db)

    def test_iter_method(self):
        self.db["one"] = 1
        self.db["two"] = 2
        self.db["three"] = 3
        self.assertEqual(list(iter(self.db)), ["one", "two", "three"])

    def test_reversed_method(self):
        self.db["one"] = 1
        self.db["two"] = 2
        self.db["three"] = 3
        self.assertEqual(list(reversed(self.db)), ["three", "two", "one"])

    def test_len_method(self):
        self.db["one"] = "foo"
        self.db["one"] = "bar"
        self.db["two"] = "baz"
        self.assertEqual(len(self.db), 2)

    def test_del_method(self):
        try:
            del self.db
            self.db = dbmw.open(filename=self.filepath, flag="r")
        except:  # noqa
            self.fail("Database did not close gracefully when deleted")

        try:
            self.db = dbmw.open(filename=os.path.join(self.tempdir, "testcopy"), flag="n")
            self.db = dbmw.open(filename=self.filepath, flag="r")
        except:  # noqa
            self.fail("Database did not close gracefully when garbage collected")

    def test_context_manager(self):
        self.db.close()

        with dbmw.open(filename=self.filepath, flag="n") as db:
            db["one"] = 1
            db["two"] = 2
            db["three"] = 3

        self.db = dbmw.open(filename=self.filepath, flag="r")
        self.assertEqual(1, self.db["one"])
        self.assertEqual(2, self.db["two"])
        self.assertEqual(3, self.db["three"])

    def test_pop_method(self):
        self.db["foo"] = "bar"
        value = self.db.pop("foo")
        self.assertEqual(value, "bar")
        self.assertTrue("one" not in self.db)

    def test_popitem_method(self):
        self.db["one"] = 1
        self.db["two"] = 2
        key, value = self.db.popitem()
        self.assertEqual(1, self.db["one"])
        self.assertEqual(key, "two")
        self.assertEqual(value, 2)
        self.assertTrue("two" not in self.db)

    def test_clear_method(self):
        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db["three"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.db.clear()
        self.assertRaises(KeyError, self.db.__getitem__, "one")
        self.assertRaises(KeyError, self.db.__getitem__, "two")
        self.assertRaises(KeyError, self.db.__getitem__, "three")

        # Clearing should compact the database
        self.db.close()
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after, before)

    def test_setdefault_method(self):
        self.db["foo"] = "bar"
        value = self.db.setdefault("foo", "baz")
        self.assertEqual(value, "bar")
        try:
            value = self.db.setdefault("one", 1)
            self.assertEqual(value, 1)
        except KeyError:
            self.fail("Setdefault should not raise KeyError.")

    def test_update_method(self):
        self.db.update({"foo": "bar", "one": 1}, two=2, foo="baz")
        self.assertEqual(self.db["foo"], "baz")
        self.assertEqual(self.db["one"], 1)
        self.assertEqual(self.db["two"], 2)

    def test_copy_method(self):

        self.db.close()
        copyfile = os.path.join(self.tempdir, "testcopy")

        for mode in ("n", "w", "c"):
            self.db = dbmw.open(filename=self.filepath, flag=mode)  # noqa
            self.db["foo"] = "bar"
            new_db = self.db.copy(copyfile)
            self.assertEqual(self.db["foo"], new_db["foo"])
            self.assertEqual(type(self.db), type(new_db))
            new_db.close()
            self.db.close()
            os.remove(new_db.filepath)

        self.db = dbmw.open(filename=self.filepath, flag="r")
        self.assertFalse(hasattr(self.db, "copy"))

    def test_covert_to_bytes(self):
        self.assertEqual(self.db._convert_to_bytes("foo"), pickle.dumps("foo", protocol=5))

    def test_covert_from_bytes(self):
        value = pickle.dumps("foo", protocol=5)
        self.assertEqual(self.db._convert_from_bytes(value), pickle.loads(value))

    def test_verify_checksums(self):
        self.db["foo"] = "bar"
        self.db.close()

        self.db = dbmw.open(self.filepath, flag="r", verify_checksums=True)

        try:
            _ = self.db["foo"]
        except dbmw.DBMChecksumError:
            self.fail("Checksum failed.")

    # --- Test compaction ----------------------------------------------------

    def test_compact(self):
        for i in range(10):
            self.db[i] = i
        for i in range(5):
            del self.db[i]

        self.db.close()
        before = os.path.getsize(self.db.filepath)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.db.compact()
        self.db.close()

        after = os.path.getsize(self.db.filepath)
        self.assertLess(after, before)

    def test_compact_does_not_leave_behind_files(self):
        before = len(os.listdir(self.tempdir))
        for i in range(10):
            self.db[i] = i
        for i in range(10):
            del self.db[i]

        self.db.close()
        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.db.compact()

        after = len(os.listdir(self.tempdir))
        self.assertEqual(before, after)

    def test_compact_on_close(self):
        self.db["foo"] = "bar"
        del self.db["foo"]
        self.db.close(compact=True)
        self.db = dbmw.open(filename=self.filepath, flag="r")
        # Only header in the file.
        self.assertEqual(self.db._current_offset, 8)

    def test_compact_set_and_get(self):
        for i in range(10):
            self.db[i] = i
        for i in range(5):
            del self.db[i]
        for i in range(5, 10):
            self.db[i] = "foo"

        self.db.compact()

        for i in range(5, 10):
            self.assertEqual(self.db[i], "foo")

        self.assertEqual(len(self.db), 5)

        for i in range(5):
            self.db[i] = i

        self.assertEqual(len(self.db), 10)

    # --- Test corrupted data ------------------------------------------------

    def test_bad_file_identifier_raises_error(self):
        self.db["foo"] = "bar"
        self.db.close()

        with open(self.db.filepath, "r") as f:
            data = f.read()

        self.assertEqual(data[:4], "dbmw")

        with open(self.db.filepath, "rb+") as f:
            f.seek(0)
            f.write(b"fdjk")

        self.assertRaises(dbmw.DBMLoadError, dbmw.open, filename=self.filepath, flag="c")

    def test_incompatible_version_number_raises_error(self):
        self.db["foo"] = "bar"
        self.db.close()

        with open(self.db.filepath, "rb+") as f:
            f.seek(4)
            f.write(struct.pack("!H", 9))

        self.assertRaises(dbmw.DBMLoadError, dbmw.open, filename=self.filepath, flag="c")

    def test_incompatible_picking_version_raises_error(self):
        self.db["foo"] = "bar"
        self.db.close()

        with open(self.db.filepath, "rb+") as f:
            f.seek(6)
            f.write(struct.pack("!H", 1))

        self.assertRaises(dbmw.DBMLoadError, dbmw.open, filename=self.filepath, flag="c")

    def test_warns_but_recovers_from_bad_key_value_size_indicator(self):
        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db["three"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        # Write garbage as the key and value indicator for the second key.
        # The first key should still be read and the db formed from that.
        with open(self.db.filepath, "r+b") as f:
            f.seek(8 + 8 + 18 + 18 + 4)
            f.write(b"\x00" * 8)

        with self.assertWarns(BytesWarning):
            self.db = dbmw.open(filename=self.filepath, flag="c")

        self.assertEqual(self.db["one"], "bar")
        self.assertRaises(KeyError, self.db.__getitem__, "two")
        self.assertRaises(KeyError, self.db.__getitem__, "three")

        # Test that compaction removes the corrupted data.
        self.db.close(compact=True)
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after, before)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.assertEqual(self.db["one"], "bar")

    def test_warns_but_recovers_from_bad_key_data(self):
        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db["three"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        # Write garbage to the beginning of the second key data.
        # The first and third key should still be read and the db formed from that.
        with open(self.db.filepath, "r+b") as f:
            f.seek(8 + 8 + 18 + 18 + 4 + 8)
            f.write(b"\x00" * 8)

        with self.assertWarns(BytesWarning):
            self.db = dbmw.open(filename=self.filepath, flag="c")

        self.assertEqual(self.db["one"], "bar")
        self.assertRaises(KeyError, self.db.__getitem__, "two")
        self.assertEqual(self.db["three"], "bar")

        # Test that compaction removes the corrupted data.
        self.db.close(compact=True)
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after, before)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.assertEqual(self.db["one"], "bar")
        self.assertEqual(self.db["three"], "bar")

    def test_warns_but_recovers_from_bad_value_data(self):
        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db["three"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        # # Write garbage to the beginning of the second value data.
        # The first and third key should still be read and the db formed from that.
        with open(self.db.filepath, "r+b") as f:
            f.seek(8 + 8 + 18 + 18 + 4 + 8 + 18)
            f.write(b"\x00" * 8)

        with self.assertWarns(BytesWarning):
            self.db = dbmw.open(filename=self.filepath, flag="c")

        self.assertEqual(self.db["one"], "bar")
        self.assertRaises(KeyError, self.db.__getitem__, "two")
        self.assertEqual(self.db["three"], "bar")

        # Test that compaction removes the corrupted data.
        self.db.close(compact=True)
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after, before)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.assertEqual(self.db["one"], "bar")
        self.assertEqual(self.db["three"], "bar")

    def test_warns_but_recovers_from_bad_checksum(self):
        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db["three"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        # # Write garbage to the beginning of the second value data.
        # The first and third key should still be read and the db formed from that.
        with open(self.db.filepath, "r+b") as f:
            f.seek(8 + 8 + 18 + 18 + 4 + 8 + 18 + 18)
            f.write(b"\x00" * 4)

        with self.assertWarns(BytesWarning):
            self.db = dbmw.open(filename=self.filepath, flag="c")

        self.assertEqual(self.db["one"], "bar")
        self.assertRaises(KeyError, self.db.__getitem__, "two")
        self.assertEqual(self.db["three"], "bar")

        # Test that compaction removes the corrupted data.
        self.db.close(compact=True)
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after, before)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.assertEqual(self.db["one"], "bar")
        self.assertEqual(self.db["three"], "bar")

    def test_warns_but_recovers_from_missing_data_at_the_end_of_the_file(self):
        # e.g. computer crashes when writing large amounts of data
        # so parts of it were not written.
        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db["three"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        self.truncate_data_file(bytes_from_end=8)

        with self.assertWarns(BytesWarning):
            self.db = dbmw.open(filename=self.filepath, flag="c")

        self.assertEqual(self.db["one"], "bar")
        self.assertEqual(self.db["two"], "bar")
        self.assertRaises(KeyError, self.db.__getitem__, "three")

        # Test that compaction removes the corrupted data.
        self.db.close(compact=True)
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after + 8, before)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.assertEqual(self.db["one"], "bar")

    def test_warns_but_recovers_from_trying_to_read_past_the_end_of_the_file(self):

        self.db["one"] = "bar"
        self.db["two"] = "bar"
        self.db.close()

        before = os.path.getsize(self.db.filepath)

        # Set value length indicator to 255 instead of 18
        with open(self.db.filepath, "r+b") as f:
            f.seek(8 + 8 + 18 + 18 + 4 + 4)
            f.write(b"\x00\x00\x00\xff")

        with self.assertWarns(BytesWarning):
            self.db = dbmw.open(filename=self.filepath, flag="c")

        self.assertEqual(self.db["one"], "bar")
        self.assertRaises(KeyError, self.db.__getitem__, "two")

        # Test that compaction removes the corrupted data.
        self.db.close(compact=True)
        after = os.path.getsize(self.db.filepath)
        self.assertLess(after + 8, before)

        self.db = dbmw.open(filename=self.filepath, flag="c")
        self.assertEqual(self.db["one"], "bar")


if __name__ == '__main__':
    unittest.main()
