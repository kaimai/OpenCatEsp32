from pathlib import Path

import petoi


def test_version():
    assert petoi.__version__ == "0.1.0"


def test_package_is_marked_typed():
    assert (Path(petoi.__file__).parent / "py.typed").exists()
