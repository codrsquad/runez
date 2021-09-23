import hashlib
import io
import os
import shutil
import tempfile
import time
from pathlib import Path

from runez.system import _R, abort, Anchored, decode, flattened, resolved_path, short, SYMBOLIC_TMP, SYS_INFO, UNSET


def basename(path, extension_marker=os.extsep, follow=False):
    """Base name of given `path`, ignoring extension if `extension_marker` is provided

    Args:
        path (str | Path | None): Path to consider
        extension_marker (str | None): If provided: trim file extension
        follow (bool): If True, follow symlink

    Returns:
        (str): Basename part of path, without extension if 'extension_marker' provided
    """
    if path:
        if follow:
            path = os.path.realpath(path)

        path = os.path.basename(path)
        if extension_marker and extension_marker in path:
            pre, _, post = path.rpartition(extension_marker)
            if pre:
                return pre

    return path


def checksum(path, hash=hashlib.sha256, blocksize=65536):
    """
    Args:
        path (str | Path | None): Path to file
        hash: Hash algorithm to use
        blocksize (int):

    Returns:
        (str): Hex-digest
    """
    if isinstance(hash, str):
        hash = getattr(hashlib, hash)

    if callable(hash):
        hash = hash()

    with open(path, "rb") as fh:
        buf = fh.read(blocksize)
        while len(buf) > 0:
            hash.update(buf)
            buf = fh.read(blocksize)

    return hash.hexdigest()


def copy(source, destination, ignore=None, overwrite=True, fatal=True, logger=UNSET, dryrun=UNSET):
    """Copy source -> destination

    Args:
        source (str | Path | None): Source file or folder
        destination (str | Path | None): Destination file or folder
        ignore (callable | list | str | None): Names to be ignored
        overwrite (bool | None): True: replace existing, False: fail if destination exists, None: no destination check
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return _file_op(source, destination, _copy, overwrite, fatal, logger, dryrun, ignore=ignore)


def delete(path, fatal=True, logger=UNSET, dryrun=UNSET):
    """
    Args:
        path (str | Path | None): Path to file or folder to delete
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    path = resolved_path(path)
    islink = path and os.path.islink(path)
    if not islink and (not path or not os.path.exists(path)):
        return 0

    if _R.hdry(dryrun, logger, "delete %s" % short(path)):
        return 1

    try:
        _do_delete(path, islink, fatal)
        _R.hlog(logger, "Deleted %s" % short(path))
        return 1

    except Exception as e:
        return abort("Can't delete %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def ensure_folder(path, clean=False, fatal=True, logger=UNSET, dryrun=UNSET):
    """Ensure folder with 'path' exists

    Args:
        path (str | Path | None): Path to file or folder
        clean (bool): True: If True, ensure folder is clean (delete any file/folder it may have)
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, >=1: successfully done, 0: was no-op, -1: failed
    """
    path = resolved_path(path)
    if not path:
        return 0

    if os.path.isdir(path):
        if not clean:
            return 0

        cleaned = 0
        for fname in os.listdir(path):
            cleaned += delete(os.path.join(path, fname), fatal=fatal, logger=None, dryrun=dryrun)

        if cleaned:
            msg = "%s from %s" % (_R.plural(cleaned, "file"), short(path))
            if not _R.hdry(dryrun, logger, "clean %s" % msg):
                _R.hlog(logger, "Cleaned %s" % msg)

        return cleaned

    if _R.hdry(dryrun, logger, "create %s" % short(path)):
        return 1

    try:
        os.makedirs(path)
        _R.hlog(logger, "Created folder %s" % short(path))

        return 1

    except Exception as e:
        return abort("Can't create folder %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def filesize(*paths, logger=False):
    """
    Args:
        *paths (str | Path | None): Paths to files/folders
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

    Returns:
        (int): File size in bytes
    """
    size = 0
    for path in flattened(paths, unique=True):
        path = to_path(path)
        if path and path.exists() and not path.is_symlink():
            if path.is_dir():
                for sf in path.iterdir():
                    size += filesize(sf)

            elif path.is_file():
                try:
                    size += path.stat().st_size

                except Exception as e:  # pragma: no cover, ignore cases like permission denied, file name too long, etc
                    _R.hlog(logger, "Can't stat %s: %s" % (short(path), short(e, size=32)))

    return size


def ini_to_dict(path, keep_empty=False, fatal=False, logger=False):
    """Contents of an INI-style config file as a dict of dicts: section -> key -> value

    Args:
        path (str | Path | None): Path to file to parse
        keep_empty (bool): If True, keep definitions with empty values
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

    Returns:
        (dict): Dict of section -> key -> value
    """
    result = {}
    section_key = None
    section = None
    for line in readlines(path, fatal=fatal, logger=logger):
        line, _, _ = line.partition("#")
        line = line.strip()
        if line:
            if line.startswith("[") and line.endswith("]"):
                section_key = line.strip("[]").strip()
                section = result.get(section_key)
                continue

            if "=" not in line:
                continue

            if section is None:
                section = result[section_key] = {}

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if keep_empty or (key and value):
                section[key] = value

    if not keep_empty:
        result = dict((k, v) for k, v in result.items() if k and v)

    return result


def is_younger(path, age, default=False):
    """
    Args:
        path (str | Path): Path to file
        age (int | float | None): How many seconds to consider the file too old
        default (bool): Returned when file is not present

    Returns:
        (bool): True if file exists and is younger than 'age' seconds
    """
    try:
        if age > 0:
            return time.time() - os.path.getmtime(path) < age

    except (OSError, IOError, TypeError):
        return default


def ls_dir(path):
    """A --dryrun friendly version of Path.iterdir

    Args:
        path (str | Path | None): Path to folder

    Yields:
        (Path): Sub-folders / files, if any
    """
    path = to_path(path)
    if path and path.is_dir():
        yield from path.iterdir()


def parent_folder(path, base=None):
    """Parent folder of `path`, relative to `base`

    Args:
        path (str | Path | None): Path to file or folder
        base (str | None): Base folder to use for relative paths (default: current working dir)

    Returns:
        (str): Absolute path of parent folder
    """
    return path and os.path.dirname(resolved_path(path, base=base))


def readlines(path, first=None, errors="ignore", fatal=False, logger=False):
    """
    Args:
        path (str | Path | None): Path to file to read lines from
        first (int | None): Return only the 'first' lines when specified
        errors (str | None): Optional string specifying how encoding errors are to be handled
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

    Yields:
        (str): Lines read, newlines and trailing spaces stripped
    """
    try:
        with io.open(resolved_path(path), errors=errors) as fh:
            if not first:
                first = -1

            for line in fh:
                if first == 0:
                    return

                yield decode(line).rstrip()
                first -= 1

    except Exception as e:
        message = "Can't read %s" % short(path)
        if fatal:
            abort(_R.actual_message(message), exc_info=e, fatal=fatal, logger=logger)

        _R.hlog(logger, message, exc_info=e)


def to_path(path, no_spaces=False):
    """
    Args:
        path (str | Path): Path to convert
        no_spaces (type | bool | None): If True-ish, abort if 'path' contains a space

    Returns:
        (Path | None): Converted to `Path` object, if necessary
    """
    if no_spaces and " " in str(path):
        abort("Refusing path with space (not worth escaping all the things to make this work): '%s'" % short(path), fatal=no_spaces)

    if isinstance(path, Path):
        return path

    if path is not None:
        if path:
            path = os.path.expanduser(path)

        return Path(path)


def move(source, destination, overwrite=True, fatal=True, logger=UNSET, dryrun=UNSET):
    """Move `source` -> `destination`

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        overwrite (bool | None): True: replace existing, False: fail if destination exists, None: no destination check
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return _file_op(source, destination, _move, overwrite, fatal, logger, dryrun)


def symlink(source, destination, must_exist=True, overwrite=True, fatal=True, logger=UNSET, dryrun=UNSET):
    """Symlink `source` <- `destination`

    Args:
        source (str | Path | None): Source file or folder
        destination (str | Path | None): Destination file or folder
        must_exist (bool): If True, verify that source does indeed exist
        overwrite (bool | None): True: replace existing, False: fail if destination exists, None: no destination check
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return _file_op(source, destination, _symlink, overwrite, fatal, logger, dryrun, must_exist=must_exist)


def compress(source, destination, arcname=UNSET, ext=None, overwrite=True, fatal=True, logger=UNSET, dryrun=UNSET):
    """
    Args:
        source (str | Path | None): Source folder to compress
        destination (str | Path | None): Destination folder
        arcname (str | None): Name of subfolder in archive (default: source basename)
        ext (str | None): Extension determining compression (default: extension of given 'source' file)
        overwrite (bool | None): True: replace existing, False: fail if destination exists, None: no destination check
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if not ext:
        _, _, ext = str(destination).lower().rpartition(".")

    kwargs = {}
    ext = SYS_INFO.platform_id.canonical_compress_extension(ext, short_form=True)
    if not ext:
        message = "Unknown extension '%s': can't compress file" % os.path.basename(destination)
        return abort(message, return_value=-1, fatal=fatal, logger=logger)

    if arcname is UNSET:
        arcname = os.path.basename(source)

    arcname = to_path(arcname or "")
    if ext == "zip":
        func = _zip

    else:
        func = _tar
        kwargs["mode"] = "w:" if ext == "tar" else "w:%s" % ext

    return _file_op(source, destination, func, overwrite, fatal, logger, dryrun, arcname=arcname, **kwargs)


def decompress(source, destination, ext=None, overwrite=True, simplify=False, fatal=True, logger=UNSET, dryrun=UNSET):
    """
    Args:
        source (str | Path | None): Source file to decompress
        destination (str | Path | None): Destination folder
        ext (str | None): Extension determining compression (default: extension of given 'source' file)
        overwrite (bool | None): True: replace existing, False: fail if destination exists, None: no destination check
        simplify (bool): If True and source has only one sub-folder, extract that one sub-folder to destination
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if not ext:
        _, _, ext = str(source).lower().rpartition(".")

    ext = SYS_INFO.platform_id.canonical_compress_extension(ext, short_form=True)
    if not ext:
        message = "Unknown extension '%s': can't decompress file" % os.path.basename(source)
        return abort(message, return_value=-1, fatal=fatal, logger=logger)

    func = _unzip if ext == "zip" else _untar
    return _file_op(source, destination, func, overwrite, fatal, logger, dryrun, simplify=simplify)


class TempFolder:
    """Context manager for obtaining a temp folder"""

    def __init__(self, anchor=True, dryrun=UNSET, follow=True):
        """
        Args:
            anchor (bool): If True, short-ify paths relative to used temp folder
            dryrun (bool): Optionally override current dryrun setting
            follow (bool): If True, change working dir to temp folder (and restore)
        """
        self.anchor = anchor
        self.dryrun = dryrun
        self.follow = follow
        self.old_cwd = None
        self.tmp_folder = None

    def __enter__(self):
        self.dryrun = _R.set_dryrun(self.dryrun)
        if not _R.is_dryrun():
            # Use realpath() to properly resolve for example symlinks on OSX temp paths
            self.tmp_folder = os.path.realpath(tempfile.mkdtemp())
            if self.follow:
                self.old_cwd = os.getcwd()
                os.chdir(self.tmp_folder)

        tmp = self.tmp_folder or SYMBOLIC_TMP
        if self.anchor:
            Anchored.add(tmp)

        return tmp

    def __exit__(self, *_):
        _R.set_dryrun(self.dryrun)
        if self.anchor:
            Anchored.pop(self.tmp_folder or SYMBOLIC_TMP)

        if self.old_cwd:
            os.chdir(self.old_cwd)

        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder, ignore_errors=True)


def touch(path, fatal=True, logger=UNSET, dryrun=UNSET):
    """Touch file with `path`

    Args:
        path (str | Path | None): Path to file to touch
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    return write(path, None, fatal=fatal, logger=logger, dryrun=dryrun)


def write(path, contents, fatal=True, logger=UNSET, dryrun=UNSET):
    """Write `contents` to file with `path`

    Args:
        path (str | Path | None): Path to file
        contents (str | bytes | None): Contents to write (only touch file if None)
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if not path:
        return 0

    path = resolved_path(path)
    byte_size = _R.represented_bytesize(len(contents)) if contents else ""

    def dryrun_msg():
        return "%s %s" % ("write %s to" % byte_size if byte_size else "touch", short(path))

    if _R.hdry(dryrun, logger, dryrun_msg):
        return 1

    ensure_folder(parent_folder(path), fatal=fatal, logger=None, dryrun=dryrun)
    try:
        mode = "wb" if isinstance(contents, bytes) else "wt"
        with io.open(path, mode) as fh:
            if contents is None:
                os.utime(path, None)

            else:
                fh.write(contents)

        _R.hlog(logger, "%s %s" % ("Wrote %s to" % byte_size if byte_size else "Touched", short(path)))
        return 1

    except Exception as e:
        return abort("Can't write to %s" % short(path), exc_info=e, return_value=-1, fatal=fatal, logger=logger)


def _copy(source, destination, ignore=None):
    """Effective copy"""
    if os.path.isdir(source):
        if os.path.isdir(destination):
            for fname in os.listdir(source):
                _copy(os.path.join(source, fname), os.path.join(destination, fname), ignore=ignore)

        else:
            if os.path.isfile(destination) or os.path.islink(destination):
                os.unlink(destination)

            shutil.copytree(source, destination, symlinks=True, ignore=ignore)

    else:
        shutil.copy(source, destination)

    shutil.copystat(source, destination)  # Make sure last modification time is preserved


def _do_delete(path, islink, fatal):
    if islink or os.path.isfile(path):
        os.unlink(path)

    else:
        shutil.rmtree(path, ignore_errors=not fatal)


def _move(source, destination):
    """Effective move"""
    shutil.move(source, destination)


def _symlink(source, destination):
    """Effective symlink"""
    source = to_path(source)
    destination = to_path(destination)
    src = source.absolute()
    dest = destination.absolute()
    if str(src.parent).startswith(str(dest.parent)):
        # Make relative symlinks automatically when applicable
        source = src.relative_to(dest.parent)

    os.symlink(source, destination)


def _tar(source, destination, arcname, mode):
    """Effective tar"""
    import tarfile

    source = to_path(source)
    delete(destination, fatal=False, logger=None, dryrun=False)
    with tarfile.open(destination, mode=mode) as fh:
        fh.add(source, arcname=arcname, recursive=True)


def _move_extracted(extracted_source, destination, simplify):
    # Tarballs often contain only one sub-folder, auto-unpack that to the destination (similar to how zip files work)
    if simplify:
        subfolders = list(ls_dir(extracted_source))
        if len(subfolders) == 1 and subfolders[0].is_dir():
            extracted_source = subfolders[0]

    delete(destination, fatal=False, logger=None, dryrun=False)
    _move(extracted_source, destination)


def _untar(source, destination, simplify):
    """Effective untar"""
    import tarfile

    source = to_path(source).absolute()
    destination = to_path(destination).absolute()
    with TempFolder():
        extracted_source = to_path(source.name)
        with tarfile.open(source) as fh:
            fh.extractall(extracted_source)

        _move_extracted(extracted_source, destination, simplify)


def _unzip(source, destination, simplify):
    """Effective unzip"""
    from zipfile import ZipFile

    source = to_path(source).absolute()
    destination = to_path(destination).absolute()
    with TempFolder():
        extracted_source = to_path(source.name)
        with ZipFile(source) as fh:
            fh.extractall(extracted_source)

        _move_extracted(extracted_source, destination, simplify)


def _zip(source, destination, arcname, fh=None):
    """Effective zip, behaving like tar+gzip for consistency"""
    if fh is None:
        from zipfile import ZipFile, ZIP_DEFLATED

        source = to_path(source).absolute()
        destination = to_path(destination).absolute()
        with ZipFile(destination, mode="w", compression=ZIP_DEFLATED) as fh:
            _zip(source, destination, arcname, fh=fh)

    elif source.is_dir():
        for f in source.iterdir():
            _zip(f, destination, arcname / f.name, fh=fh)

    else:
        fh.write(source, arcname=arcname)


def _file_op(source, destination, func, overwrite, fatal, logger, dryrun, must_exist=True, ignore=None, **extra):
    """Call func(source, destination)

    Args:
        source (str | None): Source file or folder
        destination (str | None): Destination file or folder
        func (callable): Implementation function
        overwrite (bool | None): True: replace existing, False: fail if destination exists, None: no destination check
        fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
        logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        dryrun (bool): Optionally override current dryrun setting
        must_exist (bool): If True, verify that source does indeed exist
        ignore (callable | list | str | None): Names to be ignored
        **extra: Passed-through to 'func'

    Returns:
        (int): In non-fatal mode, 1: successfully done, 0: was no-op, -1: failed
    """
    if not source or not destination or source == destination:
        return 0

    action = func.__name__[1:]
    indicator = "<-" if action == "symlink" else "->"
    description = "%s %s %s %s" % (action, short(source), indicator, short(destination))
    psource = parent_folder(source)
    pdest = resolved_path(destination)
    if psource.startswith(pdest):
        message = "Can't %s: source contained in destination" % description
        return abort(message, return_value=-1, fatal=fatal, logger=logger)

    if _R.hdry(dryrun, logger, description):
        return 1

    if must_exist and not (os.path.exists(source) or os.path.islink(source)):
        message = "%s does not exist, can't %s to %s" % (short(source), action.lower(), short(destination))
        return abort(message, return_value=-1, fatal=fatal, logger=logger)

    if overwrite is not None:
        islink = os.path.islink(pdest)
        if islink or os.path.exists(pdest):
            if not overwrite:
                message = "%s exists, can't %s" % (short(destination), action.lower())
                return abort(message, return_value=-1, fatal=fatal, logger=logger)

            _do_delete(pdest, islink, fatal)

    try:
        # Ensure parent folder exists
        ensure_folder(parent_folder(destination), fatal=fatal, logger=None, dryrun=dryrun)
        _R.hlog(logger, "%s%s" % (description[0].upper(), description[1:]))
        if ignore is not None:
            if not callable(ignore):
                given = ignore

                def ignore(*_):
                    return given

            extra["ignore"] = ignore

        func(source, destination, **extra)
        return 1

    except Exception as e:
        return abort("Can't %s" % description, exc_info=e, return_value=-1, fatal=fatal, logger=logger)
