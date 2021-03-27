"""Test DBMW performance and functionality. Be sure to run this in the command line for accuracy."""

import os
import sys
import time
import dbmw
import semidbm2
import random
import string


from typing import Generator


def _generate_random_data(length: int, ks: int, vs: int) -> Generator[tuple[bytes, bytes], None, None]:
    for i in range(length):

        # Display progress
        sys.stdout.write(f"{i + 1}/{length}\r")
        sys.stdout.flush()

        k = "".join(random.choice(string.ascii_letters) for _ in range(ks)).encode("utf-8")
        v = "".join(random.choice(string.ascii_letters) for _ in range(vs)).encode("utf-8")
        yield k, v


if __name__ == "__main__":

    print("\nBegin setup...\n")

    num_keys = 1_000_000
    keysize = 16
    valuesize = 100
    print(f"Number of keys: {num_keys}")
    print(f"Keysize: {keysize}")
    print(f"Valuesize: {valuesize}\n")

    print("Generating random data:")
    random_data: dict[bytes, bytes] = {key: value for key, value in _generate_random_data(num_keys, keysize, valuesize)}

    print("\n\nGenerating random read orders...")
    random_reads_one_percent = random.sample(list(random_data.keys()), num_keys // 100) * 100
    random_reads_all = random.sample(list(random_data.keys()), num_keys)

    print("\nSetup done! Begin testing...")

    for d in (dbmw, ):
        print("\n------------------------------------------\n")
        print(f"Testing {d.__name__}\n")
        db = d.open("_unittest_db", "n")

        start = time.time()
        for key, value in zip(random_reads_all, list(random_data.values())):
            db[key] = value
        total = time.time() - start

        print(f"Write time for {num_keys} keys randomly: {total}s.")
        print(f"{num_keys / total} ops/sec.\n")

        start = time.time()
        for key, value in random_data.items():
            db[key] = value
        total = time.time() - start

        print(f"Write time for {num_keys} keys linearly after random writes: {total}s.")
        print(f"{num_keys / total} ops/sec.\n")

        start = time.time()
        for key in random_reads_one_percent:
            _ = db[key]
        total = time.time() - start

        # Tests caching, not applicable for dbmw
        print(f"Read time for random 1% of {num_keys} keys 100 times: {total}s.")
        print(f"{len(random_reads_one_percent) / total} ops/sec.\n")

        start = time.time()
        for key in random_data.keys():
            _ = db[key]
        total = time.time() - start

        print(f"Read time for {num_keys} keys linearly: {total}s.")
        print(f"{num_keys / total} ops/sec.\n")

        start = time.time()
        for key in random_reads_all:
            _ = db[key]
        total = time.time() - start

        print(f"Read time for {num_keys} keys randomly: {total}s.")
        print(f"{num_keys / total} ops/sec.\n")

        start = time.time()
        for key in random_data.keys():
            del db[key]
        total = time.time() - start

        print(f"Deleting time for {num_keys} keys linearly: {total}s.")
        print(f"{num_keys / total} ops/sec.\n")

        start = time.time()
        db.close(compact=True)
        total = time.time() - start

        print(f"Time to close the db with compaction of {num_keys} keys: {total}s.")
        print(f"{num_keys / total} ops/sec.\n")

        try:
            os.remove("_unittest_db")
        except PermissionError:
            os.remove("_unittest_db/data")
            os.rmdir("_unittest_db")

