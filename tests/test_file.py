import hashlib
import io
import logging
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import runez
import runez.conftest

SAMPLE_CONF = """
# Sample .conf (or .ini file)
root = some-value # Definition without section

[malformed section      # Missing closing square bracket
malformed definition    # This line has no '=' sign (outside of this comment...), ignored

[] # Empty section name
ek = ev

[s1] # Some section
k1 = v1

[empty] # Empty section

[s2]
k2 =

[s3]
#k3 = v3                # This one is commented out, shouldn't show up
"""


def test_basename():
    assert runez.basename(None) is None
    assert runez.basename("") == ""
    assert runez.basename("/some-folder/bar", follow=True) == "bar"
    assert runez.basename("/some-folder/.bar") == ".bar"
    assert runez.basename("/some-folder/.bar.py") == ".bar"
    assert runez.basename("/some-folder/.bar.baz.py") == ".bar.baz"
    assert runez.basename("some-folder/bar.py") == "bar"
    assert runez.basename("some-folder/bar.baz.pyc") == "bar.baz"

    assert runez.basename("some-folder/bar.py", extension_marker=None) == "bar.py"


def test_checksum():
    sample = runez.DEV.project_path("LICENSE")
    assert runez.checksum(sample) == "0f7ae07a0fc3fccaf4e7e7888df52473abcbc2b29b47b7c2cfe8c125528e1536"
    assert runez.checksum(sample, hash=hashlib.sha1) == "ea553d4e5a18aa83ba90b575ee63a37fc9a7bc07"
    assert runez.checksum(sample, hash=hashlib.sha1()) == "ea553d4e5a18aa83ba90b575ee63a37fc9a7bc07"
    assert runez.checksum(sample, hash=hashlib.md5()) == "cbc91d983eaeb4ce4724ea3f420c5ce4"


def dir_contents(path=None):
    path = runez.to_path(path or ".")
    return {f.name: dir_contents(f) if f.is_dir() else list(runez.readlines(f)) for f in runez.ls_dir(path)}


def test_decompress(temp_folder, logged):
    runez.write("test/README.md", "hello", logger=None)
    runez.write("test/a/b", "c", logger=None)
    expected = dir_contents("test")
    test_folder = runez.to_path(temp_folder) / "test"
    assert runez.filesize(test_folder) == 6
    assert runez.represented_bytesize(test_folder) == "6 B"
    assert runez.represented_bytesize(runez.to_path("no-such-file")) == "0 B"

    # Unknown extension
    assert runez.compress("test", "test.foo", overwrite=False, fatal=False) == -1
    assert "Unknown extension 'test.foo'" in logged.pop()
    assert runez.decompress("test.foo", "somewhere", fatal=False) == -1
    assert "Unknown extension 'test.foo'" in logged.pop()

    assert runez.compress("test", "test.tar.gz", dryrun=True) == 1
    assert "Would tar test -> test.tar.gz" in logged.pop()

    assert runez.compress("test", "test.tar") == 1
    assert runez.compress("test", "test.tar.gz") == 1
    assert runez.compress("test", "test.tar.xz") == 1
    assert runez.compress("test", "test.zip") == 1
    assert "Tar test -> test.tar.gz" in logged.pop()
    size_raw = runez.filesize("test.tar")
    size_gz = runez.filesize("test.tar.gz")
    size_xz = runez.filesize("test.tar.xz")
    size_zip = runez.filesize("test.zip")
    assert size_raw > size_gz
    assert size_gz != size_xz
    if sys.version_info[:2] > (3, 8):
        # Flakey for some reason on 3.6... not sure why (.gz and .zip sizes are sometimes equal...)
        assert size_gz != size_zip

    # Tar on top of existing file
    assert runez.compress("test", "test.tar.gz", overwrite=False, fatal=False) == -1
    assert "test.tar.gz exists, can't tar" in logged.pop()

    assert runez.decompress("test.tar.gz", "unpacked", dryrun=True) == 1
    assert "Would untar test.tar.gz -> unpacked" in logged.pop()

    assert runez.decompress("test.tar.gz", "unpacked", simplify=True) == 1
    assert "Untar test.tar.gz -> unpacked" in logged.pop()
    assert dir_contents("unpacked") == expected

    # Second attempt fails without overwrite
    assert runez.decompress("test.tar.gz", "unpacked", overwrite=False, fatal=False) == -1
    assert "unpacked exists, can't untar" in logged.pop()

    # Second attempt succeeds with overwrite
    assert runez.decompress("test.tar.gz", "unpacked", simplify=True, logger=None) == 1
    assert dir_contents("unpacked") == expected

    # Check .xz file
    assert runez.decompress("test.tar.gz", "unpacked", simplify=True, logger=None) == 1
    assert dir_contents("unpacked") == expected

    # Check .zip file
    assert runez.decompress("test.zip", "unpacked", simplify=True, logger=None) == 1
    assert dir_contents("unpacked") == expected
    assert not logged

    assert runez.decompress("test.zip", "unpacked2", logger=None) == 1
    assert dir_contents("unpacked2") == {"test": expected}

    # Verify that arcname=None works correctly
    assert runez.compress("test", "test-flat.tar.gz", arcname=None) == 1
    assert runez.compress("test", "test-flat.zip", arcname=None) == 1
    assert runez.decompress("test-flat.tar.gz", "unpacked-flat-gz", logger=None) == 1
    assert runez.decompress("test-flat.zip", "unpacked-flat-zip", logger=None) == 1
    assert dir_contents("unpacked-flat-gz") == expected
    assert dir_contents("unpacked-flat-zip") == expected


def test_edge_cases():
    # Don't crash for no-ops
    assert runez.copy(None, None) == 0
    assert runez.move(None, None) == 0
    assert runez.symlink(None, None) == 0
    assert runez.copy("some-file", "some-file") == 0
    assert runez.move("some-file", "some-file") == 0
    assert runez.symlink("some-file", "some-file") == 0
    assert runez.delete("non-existing") == 0

    assert runez.touch(None) == 0
    assert not runez.file.is_younger("", None)
    assert not runez.file.is_younger("", 1)
    assert not runez.file.is_younger("/dev/null/not-there", 1)


def test_ensure_folder(temp_folder, logged):
    assert runez.ensure_folder(None) == 0
    assert runez.ensure_folder("") == 0
    assert runez.ensure_folder(".") == 0
    assert not logged

    assert runez.ensure_folder("foo") == 1
    assert "Created folder foo" in logged.pop()

    assert runez.ensure_folder(".", clean=True) == 1
    assert "Cleaned 1 " in logged.pop()

    assert runez.touch("some-file", logger=None) == 1
    with pytest.raises(runez.system.AbortException):
        runez.ensure_folder("some-file")
    assert "Can't create folder" in logged.pop()

    assert runez.ensure_folder("some-dir", dryrun=True) == 1
    assert "Would create some-dir" in logged.pop()
    assert runez.ensure_folder("some-dir") == 1
    assert "Created folder some-dir" in logged.pop()

    assert runez.ensure_folder("some-dir") == 0
    assert not logged

    assert runez.touch("some-dir/a/b") == 1
    assert "Created folder" not in logged
    assert "Touched some-dir/a/b" in logged.pop()
    assert runez.ensure_folder("some-dir", clean=True, dryrun=True) == 1
    assert "Would clean 1 file from some-dir" in logged.pop()

    assert runez.touch("some-dir/b", logger=False) == 1
    assert not logged

    assert runez.ensure_folder("some-dir", clean=True) == 2
    assert "Cleaned 2 files from some-dir" in logged


def test_ini_to_dict(temp_folder, logged):
    assert runez.file.ini_to_dict(None) == {}
    assert runez.file.ini_to_dict("foo") == {}
    assert not logged

    with pytest.raises(runez.system.AbortException, match="Can't read foo"):
        runez.file.ini_to_dict("foo", fatal=True)

    assert "Can't read foo" in logged.pop()

    expected = {None: {"root": "some-value"}, "": {"ek": "ev"}, "s1": {"k1": "v1"}, "s2": {"k2": ""}}
    sample = "test.ini"
    runez.write(sample, SAMPLE_CONF, logger=None)

    actual = runez.file.ini_to_dict(sample, keep_empty=True, logger=None)
    assert not logged
    assert actual == expected

    del expected[None]
    del expected[""]
    del expected["s2"]
    actual = runez.file.ini_to_dict("test.ini", keep_empty=False)
    assert not logged
    assert actual == expected


def test_failure(monkeypatch):
    monkeypatch.setattr(io, "open", runez.conftest.exception_raiser())
    monkeypatch.setattr(os, "unlink", runez.conftest.exception_raiser("bad unlink"))
    monkeypatch.setattr(shutil, "copy", runez.conftest.exception_raiser())
    monkeypatch.setattr(os.path, "exists", lambda _: True)
    monkeypatch.setattr(os.path, "isfile", lambda _: True)
    monkeypatch.setattr(os.path, "getsize", lambda _: 10)
    with runez.CaptureOutput() as logged:
        with patch("runez.file._do_delete"):
            with patch("pathlib.Path.exists", return_value=True):
                assert runez.copy("some-file", "bar", fatal=False) == -1
                assert "Can't copy" in logged.pop()

        assert runez.delete("some-file", fatal=False) == -1
        assert "Can't delete" in logged
        assert "bad unlink" in logged.pop()

        assert runez.write("bar", "some content", fatal=False)
        assert "Can't write" in logged.pop()

        if not runez.SYS_INFO.platform_id.is_windows:
            assert runez.make_executable("some-file", fatal=False) == -1
            assert "Can't chmod" in logged.pop()


def test_file_inspection(temp_folder, logged):
    assert runez.touch("sample") == 1
    assert runez.delete("sample") == 1
    assert "Deleted sample" in logged.pop()

    assert runez.ensure_folder("sample") == 1
    assert runez.delete("sample") == 1
    assert "Deleted sample" in logged.pop()

    sample = runez.DEV.tests_path("sample.txt")
    assert len(list(runez.readlines(sample))) == 4
    assert len(list(runez.readlines(sample, first=1))) == 1
    unstripped_lines = list(runez.readlines(sample, first=1, transform=None))
    assert len(unstripped_lines) == 1
    assert unstripped_lines[0].endswith("\n")
    assert not logged

    cc = "%s\n" % "\n".join(runez.readlines(sample))
    assert runez.write("sample", cc, fatal=False, logger=logging.debug) == 1
    cc2 = "%s\n" % "\n".join(runez.readlines("sample"))
    assert cc2 == cc
    assert "Wrote sample" in logged.pop()

    assert list(runez.readlines("sample", first=2)) == ["", "Fred"]
    assert runez.file.is_younger("sample", age=10)
    assert not runez.file.is_younger("sample", age=-1)

    # Verify that readlines() can ignore encoding errors
    with io.open("not-a-text-file", "wb") as fh:
        fh.write(b"\x89 hello\nworld")

    assert list(runez.readlines("not-a-text-file", first=1)) == [" hello"]
    assert not logged

    assert runez.copy("bar", "baz", fatal=False) == -1
    assert "does not exist" in logged.pop()
    assert runez.move("bar", "baz", fatal=False) == -1
    assert "does not exist" in logged.pop()
    assert runez.symlink("bar", "baz", fatal=False) == -1
    assert "does not exist" in logged.pop()

    # Creating dangling symlinks is possible
    assert runez.symlink("s/bar", "s/baz", fatal=False, must_exist=False) == 1
    assert "Symlink s/bar <- s/baz" in logged.pop()
    assert os.path.islink("s/baz")
    assert not os.path.exists("s/baz")
    runez.touch("s/bar")
    assert os.path.exists("s/baz")

    assert runez.copy("sample", "x/y/sample") == 1
    assert runez.symlink("sample", "x/y/sample3", fatal=False) == 1

    assert os.path.exists("sample")
    assert runez.move("sample", "x/y/sample2") == 1
    assert not os.path.exists("sample")

    assert runez.copy("x/y", "x/z1") == 1
    assert os.path.exists("x/z1/sample")
    assert os.path.exists("x/z1/sample2")
    assert os.path.exists("x/z1/sample3")
    assert os.path.islink("x/z1/sample3")

    assert runez.copy("x/y", "x/z2", ignore={"sample2"}) == 1
    assert os.path.exists("x/z2/sample")
    assert not os.path.exists("x/z2/sample2")
    assert os.path.exists("x/z2/sample3")
    assert os.path.islink("x/z2/sample3")

    def should_ignore(src, dest):
        if src == "x/y" and "sample3" in dest:
            return {"sample3"}

    assert runez.copy("x/y", "x/z3", ignore=should_ignore) == 1
    assert os.path.exists("x/z3/sample")
    assert os.path.exists("x/z3/sample2")
    assert not os.path.exists("x/z3/sample3")

    assert runez.copy("x/y", "x/z2") == 1
    assert os.path.exists("x/z2/sample2")

    # Copy a folder over an existing file
    runez.touch("x2")
    assert not os.path.exists("x2/z2/sample2")
    assert runez.copy("x", "x2") == 1
    assert os.path.exists("x2/z2/sample2")


def test_file_operations(temp_folder):
    runez.symlink("foo", "dangling-symlink", must_exist=False)
    runez.move("dangling-symlink", "dangling-symlink2")
    assert os.path.islink("dangling-symlink2")

    runez.write("README.md", "hello")
    runez.copy("README.md", "sample1/README.md")
    runez.copy("sample1", "sample2")
    runez.move("sample1/README.md", "sample1/foo")

    # overwrite=None "merges" dir contents
    runez.copy("sample1", "sample2", overwrite=None)
    assert dir_contents("sample2") == {"README.md": ["hello"], "foo": ["hello"]}

    # overwrite=True replaces dir
    runez.copy("sample1", "sample2", overwrite=True)
    assert dir_contents("sample2") == {"foo": ["hello"]}

    # overwrite=None, source is a dir, existing destination file gets replaced by source directory
    runez.copy("sample1", "sample2/foo", overwrite=None)
    assert dir_contents("sample2") == {"foo": {"foo": ["hello"]}}

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.ensure_folder("some-folder", fatal=False) == 1
        assert "Would create" in logged.pop()

        assert runez.touch("some-file", logger=logging.debug) == 1
        assert "Would touch some-file" in logged.pop()

        assert runez.copy("some-file", "bar") == 1
        assert "Would copy some-file -> bar" in logged.pop()

        assert runez.move("some-file", "bar") == 1
        assert "Would move some-file -> bar" in logged.pop()

        assert runez.symlink("some-file", "bar") == 1
        assert "Would symlink some-file <- bar" in logged.pop()

        assert runez.delete(temp_folder) == 1
        assert "Would delete" in logged.pop()

        assert runez.copy("some-folder/bar", "some-folder", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

        assert runez.move("some-folder/bar/baz", "some-folder", fatal=False) == -1
        assert "source contained in destination" in logged.pop()

        assert runez.symlink("some-folder/bar/baz", "some-folder", fatal=False) == -1
        assert "source contained in destination" in logged.pop()


def test_pathlib(temp_folder):
    subfolder = runez.to_path(temp_folder) / "subfolder"
    assert runez.to_path(subfolder) is subfolder
    assert not subfolder.is_dir()
    runez.ensure_folder(subfolder)
    assert subfolder.is_dir()

    with pytest.raises(ValueError, match="Refusing path with space"):
        runez.to_path("foo bar", no_spaces=ValueError)

    with runez.CurrentFolder(subfolder, anchor=True):
        path = Path("foo")
        assert runez.short(path) == "foo"
        assert runez.short(path.absolute()) == "foo"

        assert runez.resolved_path(path)
        assert runez.parent_folder(path) == os.path.join(temp_folder, "subfolder")
        assert runez.touch(path) == 1
        assert runez.copy(path, Path("bar")) == 1
        assert runez.copy(Path("bar"), Path("baz")) == 1

        foo_json = Path("foo.json")
        runez.write(path, '{"a": "b"}')
        runez.symlink(path, foo_json)
        assert runez.read_json(foo_json) == {"a": "b"}
        assert list(runez.readlines(foo_json)) == ['{"a": "b"}']

        assert runez.basename(foo_json.absolute()) == "foo"


def test_parent_folder():
    cwd = os.getcwd()

    assert runez.parent_folder(None) is None
    assert runez.parent_folder("././some-file") == cwd

    if not runez.SYS_INFO.platform_id.is_windows:
        parent = runez.parent_folder("/logs/foo")
        assert parent == "/logs"
        assert runez.parent_folder(parent) == "/"
        assert runez.parent_folder("/") == "/"
