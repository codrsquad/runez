"""
Make sure 'from runez import *' (not recommended!) works correctly
"""

from runez import *  # noqa: F403


def test_import():
    names = [name for name in globals() if not name.startswith(("_", "@"))]
    assert len(names) > 10
    assert "short" in names

    assert short("foo") == "foo"  # noqa: F405
