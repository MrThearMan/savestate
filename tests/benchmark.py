"""Test SaveState performance and functionality. Be sure to run this from the command line for accuracy."""

import argparse
import random
import shutil
import string
import sys
import time
from typing import Generator

from tests.conftest import SAVESTATE_DIR, SAVESTATE_FILE, clear_savestate_dir


__all__ = []


def _log_on_same_line(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def _generate_random_data(length: int, ks: int, vs: int) -> Generator[tuple[bytes, bytes], None, None]:
    for i in range(length):

        # Display progress
        _log_on_same_line(f" {i + 1}/{length}\r")

        k = "".join(random.choice(string.ascii_letters) for _ in range(ks))  # .encode("utf-8")
        v = "".join(random.choice(string.ascii_letters) for _ in range(vs))  # .encode("utf-8")
        yield k, v


if __name__ == "__main__":

    import shelve

    import savestate

    print("\n Begin setup...\n")

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", dest="num_keys", type=int, default=100_000)
    parser.add_argument("-ks", dest="keysize", type=int, default=16)
    parser.add_argument("-vs", dest="valuesize", type=int, default=100)
    parser.add_argument("-c", dest="compact", type=bool, default=True)
    args = parser.parse_args()

    print(f" Number of keys: {args.num_keys}")
    print(f" Keysize: {args.keysize}")
    print(f" Valuesize: {args.valuesize}")

    print("\n Generating random data...")
    random_data: dict[bytes, bytes] = {
        key: value for key, value in _generate_random_data(args.num_keys, args.keysize, args.valuesize)
    }

    print("\n\n Generating random read orders...")
    random_reads_one_percent = random.sample(list(random_data.keys()), args.num_keys // 100) * 100
    random_reads_all = random.sample(list(random_data.keys()), args.num_keys)

    print("\n Setup done! Begin testing...\n")

    # If you wish to compare performance with another library,
    # import it and add it to the list here. It must implement:
    # 'open', 'close', '__getitem__', '__setitem__' and '__delitem__'
    for d, file in [(savestate, SAVESTATE_FILE), (shelve, str(SAVESTATE_FILE))]:
        print(" ------------------------------------------\n")
        print(f" Testing {d.__name__}\n")

        clear_savestate_dir()
        with d.open(file, "n") as db:

            # --- Write random --------------------------------------------------------------

            start = time.time()
            for key, value in zip(random_reads_all, list(random_data.values())):
                db[key] = value
            total = time.time() - start

            print(f" Write time for {args.num_keys} keys randomly: {total:.2f}s.")
            print(f" {(args.num_keys / total):.0f} ops/sec.\n")

            # --- Write sequential ----------------------------------------------------------

            start = time.time()
            for key, value in random_data.items():
                db[key] = value
            total = time.time() - start

            print(f" Write time for {args.num_keys} keys linearly after random writes: {total:.2f}s.")
            print(f" {(args.num_keys / total):.0f} ops/sec.\n")

            # --- Read sequential -----------------------------------------------------------

            start = time.time()
            for key in list(random_data.keys()):
                _ = db[key]
            total = time.time() - start

            print(f" Read time for {args.num_keys} keys linearly: {total:.2f}s.")
            print(f" {(args.num_keys / total):.0f} ops/sec.\n")

            # --- Read random ---------------------------------------------------------------

            start = time.time()
            for key in random_reads_all:
                _ = db[key]
            total = time.time() - start

            print(f" Read time for {args.num_keys} keys randomly: {total:.2f}s.")
            print(f" {(args.num_keys / total):.0f} ops/sec.\n")

            # --- Read hot -------------------------------------------------------------------

            start = time.time()
            for key in random_reads_one_percent:
                _ = db[key]
            total = time.time() - start

            # Tests caching, not applicable to savestate
            print(f" Read time for random 1% of {args.num_keys} keys 100 times: {total:.2f}s.")
            print(f" {(len(random_reads_one_percent) / total):.0f} ops/sec.\n")

            # --- Delete sequential ----------------------------------------------------------

            if sys.platform.startswith("win") and d.__name__ == "shelve":
                print(" Shelve is so slow for deletion on windows it's not worth testing.\n")

            else:
                start = time.time()
                for key in list(random_data.keys()):
                    del db[key]
                # SaveState will try to compact its data (a bit slower but not that much).
                if args.compact and hasattr(db, "compact"):
                    db.compact()
                total = time.time() - start

                print(f" Deleting time for {args.num_keys} keys linearly: {total:.2f}s.")
                print(f" {(args.num_keys / total):.0f} ops/sec.\n")

            # --------------------------------------------------------------------------------

        shutil.rmtree(SAVESTATE_DIR)
