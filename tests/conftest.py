import shutil
from pathlib import Path

import pytest

import savestate


__all__ = [
    "truncate_data_file",
    "SAVESTATE_DIR",
    "SAVESTATE_FILE",
    "clear_savestate_dir",
]


SAVESTATE_DIR = Path(__file__).parent / "testdir"
SAVESTATE_FILE = SAVESTATE_DIR / "testfile"


@pytest.fixture(autouse=True)
def clear_dir():
    clear_savestate_dir()


@pytest.fixture
def savestate_db(clear_dir):
    with savestate.open(filename=SAVESTATE_FILE, flag="n") as file:
        yield file


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    request.addfinalizer(lambda: shutil.rmtree(SAVESTATE_DIR))


def truncate_data_file(filepath: Path, bytes_from_end: int) -> None:
    with open(filepath, "rb") as f:
        data = f.read()
    with open(filepath, "wb") as f:
        f.write(data[:-bytes_from_end])


def clear_savestate_dir() -> None:
    if SAVESTATE_DIR.exists():
        shutil.rmtree(SAVESTATE_DIR)
    SAVESTATE_DIR.mkdir()
