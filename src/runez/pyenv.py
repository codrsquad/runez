import logging
import os
import re
import sys
from collections import defaultdict

from runez.program import is_executable, run
from runez.system import _R, abort, cached_property, flattened, resolved_path, short, UNSET


CPYTHON_NAMES = ["python", "", "p", "py", "cpython"]
R_SPEC = re.compile(r"^\s*((|py?|c?python|(ana|mini)?conda[23]?|pypy)\s*[:-]?)\s*([0-9]*)\.?([0-9]*)\.?([0-9]*)\s*$", re.IGNORECASE)
R_VERSION = re.compile(r"^((\d+)((\.(\d+))*)((a|b|c|rc)(\d+))?(\.(dev|post|final)\.?(\d+))?).*$")
LOG = logging.getLogger(__name__)


def _simplified_python_path(path):
    """Simplify macos ridiculous paths"""
    if path and ".framework/" in path:
        location = "/usr/bin"
        if "Cellar" in path:
            i = path.index("Cellar")
            location = path[:i].rstrip("/")
            if not location.endswith("bin"):
                location = os.path.join(location, "bin")

        if "Versions/3" in path:
            return os.path.join(location, "python3")

        if "Versions/2" in path:
            return os.path.join(location, "python2")

    return path


class PrioritizedName(object):
    """Name with an assigned sorting priority"""

    def __init__(self, name, priority):
        self.name = name
        self.priority = priority

    def __repr__(self):
        return self.name

    def __lt__(self, other):
        if isinstance(other, PrioritizedName):
            return self.priority < other.priority

    def __eq__(self, other):
        return isinstance(other, PrioritizedName) and self.priority == other.priority


class OrderedByName(object):
    """Allows to order things arbitrarily by name"""

    def __init__(self, order=None, reverse=True, separator=","):
        order = flattened(order, split=separator, keep_empty=None)
        for name in self.__slots__:
            if name not in order:
                order.append(name)

        count = len(order)
        for i, name in enumerate(order):
            obj = PrioritizedName(name, count - i if reverse else i)
            setattr(self, name, obj)

    @property
    def effective_order(self):
        return sorted([getattr(self, n) for n in self.__slots__], reverse=True)

    def __repr__(self):
        return ",".join(str(s) for s in self.effective_order)


class Origins(OrderedByName):
    """
    Scanned python installations are sorted by where they came from, in this default order (highest priority first):
    - adhoc: python installations that were explicitly given by user, via full path to python exe
    - pyenv: pyenv-like installations (very quick to scan)
    - invoker: the python that we're currently running under
    - path: PATH-like env var (slower to scan), this
    """

    __slots__ = ["adhoc", "pyenv", "invoker", "path"]


class Families(OrderedByName):
    """Allows to sort installations by python family"""

    __slots__ = ["cpython", "pypy", "conda"]

    @property
    def default_family(self):
        return self.cpython

    def guess_family(self, text):
        """Guessed python family from given 'text' (typically path to installation)"""
        if text:
            for name in self.__slots__:
                if name in text:
                    return getattr(self, name)

        return self.default_family


class PythonSpec(object):
    """
    Holds a canonical reference to a desired python installation
    Examples: 3, 3.9, py39, conda3.7.1, /usr/bin/python
    """

    def __init__(self, text, family):
        """
        Args:
            text (str): Text describing desired python
            family (PrioritizedName): Corresponding python family
        """
        text = text.strip() if text else ""
        self.family = family
        self.text = text
        self.version = None
        if text in CPYTHON_NAMES:
            self.canonical = "%s" % family
            return

        if os.path.isabs(text) or text.startswith("~") or "/" in text:
            self.canonical = resolved_path(text)
            return

        self.canonical = "?%s" % text  # Don't let arbitrary given text accidentally count as valid canonical
        m = R_SPEC.match(text)
        if not m:
            return

        components = [s for s in (m.group(4), m.group(5), m.group(6)) if s]
        if len(components) == 1:
            components = [c for c in components[0]]  # Support notation of the form: py37

        if components and len(components) <= 3:
            self.version = Version(".".join(components))
            self.canonical = "%s:%s" % (family, self.version.text)

    def __repr__(self):
        return short(self.canonical)

    def __eq__(self, other):
        return isinstance(other, PythonSpec) and self.canonical == other.canonical

    def __lt__(self, other):
        if isinstance(other, PythonSpec):
            if self.family == other.family:
                if self.version:
                    return other.version and self.version < other.version

                return other.version or self.canonical < other.canonical

            return self.family < other.family


class PythonDepot(object):
    """
    Scan usual locations to discover python installations.
    2 types of location are scanned:
    - pyenv-like folders (very quick scan, scanned immediately)
    - PATH-like env vars (slower scan, scanned as late as possible)
    - 'locations' is accepted as a ':'-separated string, to make configuration easier

    Example usage:
        my_depot = PythonDepot(locations="~/.pyenv:$PATH")
        p = my_depot.find_python("3.7")
    """

    available = None  # type: list[PythonInstallation]  # Available installations (used to find pythons by spec)
    invalid = None  # type: list[PythonInstallation]  # Invalid python installations found
    _cache = None  # type: dict[str, PythonInstallation]
    _path_scanned = False

    def __init__(self, pyenv="~/.pyenv", use_invoker=True, use_path=True):
        """
        Args:
            pyenv (str | list[str] | None): pyenv-like installations to scan (multiple possible, ':'-separated)
            use_invoker (bool): If True, make python we're currently running under ("invoker") part of 'self.available' pythons
            use_path (bool): If True, scan $PATH for python installations as well (this is done "as late as possible")
        """
        self.pyenv = pyenv
        self.use_invoker = use_invoker
        self.use_path = use_path
        self.families = Families()
        self.origin = Origins()
        self.rescan()

    def rescan(self, scan_path=False):
        """Rescan configured locations for python installations

        Args:
            scan_path (bool): If True, scan PATH env var immediately
        """
        self.available = []
        self.invalid = []
        self._cache = {}
        self._path_scanned = not self.use_path
        self._scan_pyenv()
        if self.use_invoker:
            self._register(self.invoker)

        if scan_path:
            self.scan_path_env_var(sort=False)

        self._sort()

    @cached_property
    def invoker(self):
        """Python we're currently running under"""
        return InvokerPython(self)

    def find_python(self, spec, fatal=False, logger=UNSET):
        """
        Args:
            spec (str | PythonSpec | None): Example: 3.7, py37, pypy3.7, conda3.7, /usr/bin/python
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter

        Returns:
            (PythonInstallation): Object representing python installation (may not be usable, see reported .problem)
        """
        if not isinstance(spec, PythonSpec):
            python = self._cache.get(spec)
            if python:
                return self._checked_pyinstall(python, fatal)

            spec = self.spec_from_text(spec)

        python = self._cache.get(spec.canonical)
        if python:
            return self._checked_pyinstall(python, fatal)

        if spec.canonical and os.path.isabs(spec.canonical):
            python = self.python_from_path(spec.canonical, logger=logger)  # Absolute path: look it up and remember it
            return self._checked_pyinstall(python, fatal)

        for python in self.available:
            if python.satisfies(spec):
                return python

        from_path = self.scan_path_env_var(logger=logger)
        if from_path:
            for python in from_path:
                if python.satisfies(spec):
                    return python

        python = UnknownPython(self, self.origin.adhoc, spec.canonical)
        return self._checked_pyinstall(python, fatal)

    def scan_path_env_var(self, logger=UNSET, sort=True):
        """Ensure env vars locations are scanned

        Args:
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            sort (bool): Internal, used to minimize number of times self.available gets sorted

        Returns:
            (list[PythonInstallation] | None): Installations
        """
        if self._path_scanned:
            return None

        self._path_scanned = True
        found = []
        real_paths = defaultdict(set)
        for folder in flattened(os.environ.get("PATH"), split=os.pathsep, keep_empty=None):
            for path in self.python_exes_in_folder(folder):
                real_path = os.path.realpath(path)
                if real_path not in self._cache:
                    real_paths[real_path].add(path)

        for real_path, paths in real_paths.items():
            python = self.python_from_path(real_path, equivalents=paths, origin=self.origin.path, logger=logger, sort=False)
            if python.origin is self.origin.path:
                found.append(python)

        _R.hlog(logger, "Found %s pythons in $PATH" % (len(found)))
        if sort and found:
            self._sort()

        return sorted(found, reverse=True)

    def _cached_equivalents(self, python):
        count = 0
        if python.executable not in self._cache:
            self._cache[python.executable] = python
            count += 1

        for p in python.equivalent:
            if p not in self._cache:
                self._cache[p] = python
                count += 1

        return count

    def python_from_path(self, path, equivalents=None, origin=None, logger=UNSET, sort=True):
        """
        Args:
            path (str): Path to python executable
            equivalents (list | set | None): Additional equivalent paths
            origin (OrderedByName | None): Optional, origin that triggered the scan
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            sort (bool): Internal, used to minimize number of times self.available gets sorted

        Returns:
            (PythonInstallation): Corresponding python installation
        """
        effective_origin = origin or self.origin.adhoc
        if equivalents is None:
            python = self._cache.get(path)
            if python:
                return python

            exe = self.resolved_python_exe(path)
            if not exe:
                python = UnknownPython(self, effective_origin, path)
                self._register(python)
                return python

            if path != exe:
                path = exe
                python = self._cache.get(path)
                if python:
                    return python

        python = PythonFromPath(self, effective_origin, path, equivalents=equivalents)
        if self._register(python):
            if origin is None:
                _R.hlog(logger, "Found %s python: %s" % (effective_origin, python))

            if sort:
                self._sort()

        return python

    def spec_from_text(self, text, family=None):
        """
        Args:
            text (str): Given text describing a desired python
            family (PrioritizedName | str | None): Optional alternative text to examine to guess family

        Returns:
            (PythonSpec): Object formalizing how that spec is handled internally
        """
        if not isinstance(family, PrioritizedName):
            family = self.families.guess_family(family or text)

        return PythonSpec(text, family)

    def python_exes_in_folder(self, path):
        """
        Args:
            path (str): Path to python exe or folder with a python installation

        Returns:
            Yields all python executable names
        """
        if path:
            path = resolved_path(path)
            if os.path.isdir(path):
                bin_folder = os.path.join(path, "bin")
                if os.path.isdir(bin_folder):
                    path = bin_folder

                for name in ("python", "python3", "python2"):
                    candidate = os.path.join(path, name)
                    if is_executable(candidate):
                        yield candidate

            elif is_executable(path):
                yield path

    def resolved_python_exe(self, path):
        """Find python executable from 'path'
        Args:
            path (str): Path to a bin/python, or a folder containing bin/python

        Returns:
            (str): Full path to bin/python, if any
        """
        for exe in self.python_exes_in_folder(path):
            return exe

    def _sort(self):
        self.available = sorted(self.available, reverse=True)

    def _scan_pyenv(self, logger=UNSET):
        for location in flattened(self.pyenv, split=":", keep_empty=None):
            location = resolved_path(location)
            if location and os.path.isdir(location):
                count = 0
                pv = os.path.join(location, "versions")
                if os.path.isdir(pv):
                    location = pv

                for fname in os.listdir(location):
                    folder = os.path.join(location, fname)
                    spec = self.spec_from_text(fname, folder)
                    if spec.version:
                        python = PythonPyenvInstallation(self, self.origin.pyenv, folder, spec)
                        count += self._register(python)

                _R.hlog(logger, "Found %s pythons in %s" % (count, short(location)))

    def _register(self, python):
        """
        Args:
            python (PythonInstallation): Python installation to register

        Returns:
            (int): 1 if registered (0 if python was invalid, or already known)
        """
        if self._cached_equivalents(python):
            if not python.problem:
                self.available.append(python)
                return 1

            self.invalid.append(python)

        return 0

    @staticmethod
    def _checked_pyinstall(python, fatal):
        """Optionally abort if 'python' installation is not valid"""
        if fatal and python.problem:
            abort("Invalid python installation: %s" % python)

        return python


class Version(object):
    """
    Parse versions according to PEP-0440, ordering for non pre-releases is well supported
    Pre-releases are partially supported, no complex combinations (such as ".post.dev") are paid attention to
    """

    def __init__(self, text, max_parts=4):
        self.text = text
        self.components = None
        self.prerelease = None
        m = R_VERSION.match(text)
        if not m:
            return

        self.text, major, main_part, pre, pre_num, rel, rel_num = m.group(1, 2, 3, 7, 8, 10, 11)
        if rel:
            rel = rel.lower()

        components = (major + main_part).split(".")
        if len(components) > max_parts:
            return  # Invalid version

        while len(components) < max_parts:
            components.append(0)

        if rel in ("final", "post"):
            components.append(rel_num or 0)

        else:
            components.append(0)

        self.components = tuple(map(int, components))
        pre = "dev" if rel == "dev" else "_" + pre if pre else None  # Ensure 'dev' is sorted higher than other pre-release markers
        if pre:
            self.prerelease = (pre, int(pre_num or 0))

    @classmethod
    def from_text(cls, text):
        v = cls(text)
        if v.is_valid:
            return v

    def __repr__(self):
        return self.text

    def __hash__(self):
        return hash(self.text)

    def __eq__(self, other):
        return isinstance(other, Version) and self.components == other.components and self.prerelease == other.prerelease

    def __lt__(self, other):
        if isinstance(other, Version):
            if self.components == other.components:
                if self.prerelease:
                    return other.prerelease and self.prerelease < other.prerelease

                return other.prerelease

            return self.components < other.components

    @property
    def is_valid(self):
        return self.components is not None

    @property
    def main(self):
        if self.components:
            return "%s.%s.%s" % (self.major, self.minor, self.patch)

    @property
    def major(self):
        return self.components and self.components[0]

    @property
    def minor(self):
        return self.components and self.components[1]

    @property
    def patch(self):
        return self.components and self.components[2]


class PythonInstallation(object):
    """Models a specific python installation"""

    equivalent = None  # type: set[str] # Paths that are equivalent to this python installation
    executable = None  # type: str # Full path to python executable
    family = None  # type: PrioritizedName
    is_venv = None  # type: bool # Is this python installation a venv?
    problem = None  # type: str # String describing a problem with this installation, if there is one
    spec = None  # type: PythonSpec # Corresponding spec
    origin = None  # type: PrioritizedName # Where this installation came from (pyenv, invoker, PATH, ...)

    def __init__(self, depot, origin, exe, equivalents=None, spec=None):
        """
        Args:
            depot (PythonDepot): Associated depot
            origin (PrioritizedName): Where this installation came from (pyenv, invoker, PATH, ...)
            exe (str): Path to executable
            equivalents (list | set | None): Optional equivalent identifiers for this installation
            spec (PythonSpec | None): Associated spec
        """
        self.depot = depot
        self.executable = _simplified_python_path(exe)
        self.equivalent = {exe, self.executable}
        self.origin = origin
        self.spec = spec
        if equivalents:
            self.equivalent.update(equivalents)

    def __repr__(self):
        return self.representation(colored=False, include_origin=False)

    def __eq__(self, other):
        return isinstance(other, PythonInstallation) and self.executable == other.executable

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        if isinstance(other, PythonInstallation):
            if self.origin == other.origin:
                if self.spec:
                    return other.spec and self.spec < other.spec

                return other.spec

            return self.origin < other.origin

    @property
    def family(self):
        """Python family"""
        return self.spec and self.spec.family

    @property
    def major(self):
        """Major python version, if any"""
        return self.spec and self.spec.version and self.spec.version.major

    @property
    def version(self):
        """Python version, if any"""
        return self.spec and self.spec.version

    @property
    def short_name(self):
        """Shortened representation of self.executable"""
        return short(self.executable)

    def representation(self, colored=True, include_origin=True):
        """Colored textual representation of this python installation"""
        if colored:
            rm = _R._runez_module()
            bold = rm.bold
            dim = rm.dim
            orange = rm.orange
            red = rm.red

        else:
            bold = dim = orange = red = str

        note = "[%s]" % (self.problem or self.spec.canonical)
        note = red(note) if self.problem else dim(note)
        if include_origin:
            note += orange(dim(" [%s]" % self.origin))

        if self.is_venv:
            note += orange(" [venv]")

        return "%s %s" % (bold(self.short_name), note)

    def satisfies(self, spec):
        """
        Args:
            spec (PythonSpec): Spec expressed by user or configuration

        Returns:
            (bool): True if this python installation satisfies it
        """
        if not self.problem:
            return spec.canonical in self.equivalent or self.spec.canonical.startswith(spec.canonical)


class InvokerPython(PythonInstallation):
    """Python we're currently running under"""

    def __init__(self, depot):
        version = sys.version_info[:3]
        major = version[0]
        version = ".".join(str(c) for c in version)
        prefix = getattr(sys, "real_prefix", None)  # old py2 case
        if not prefix:
            prefix = getattr(sys, "base_prefix", sys.prefix)

        if not prefix:
            parent = sys.executable

        else:
            parent = os.path.join(prefix, "bin/python%s" % major)
            if not is_executable(parent):
                parent = os.path.join(prefix, "bin/python")

        family_text = getattr(sys, "implementation", None)
        if family_text:
            family_text = getattr(family_text, "name", None)

        real_path = os.path.realpath(parent)
        equivalents = {"invoker", parent, real_path}
        family = depot.families.guess_family(family_text or real_path)
        spec = depot.spec_from_text(version, family)
        super(InvokerPython, self).__init__(depot, depot.origin.invoker, real_path, equivalents=equivalents, spec=spec)


class PythonPyenvInstallation(PythonInstallation):
    """Models a pyenv-style installation"""

    def __init__(self, depot, origin, folder, spec):
        self.folder = folder
        exes = []
        for path in depot.python_exes_in_folder(folder):
            if not exes:
                exes.append(os.path.realpath(path))

            exes.append(path)

        if not exes:
            exes.append(os.path.join(folder, "bin", "python"))
            self.problem = "invalid pyenv installation"

        super(PythonPyenvInstallation, self).__init__(depot, origin, exes[0], equivalents=exes, spec=spec)

    @property
    def short_name(self):
        return short(self.folder)


class PythonFromPath(PythonInstallation):
    """Python installation from a specific local path"""

    def __init__(self, depot, origin, exe, equivalents=None):
        super(PythonFromPath, self).__init__(depot, origin, exe, equivalents=equivalents)
        self.base_prefix = None
        self.prefix = None
        pv = _Introspect.get_pv()
        r = run(exe, pv, dryrun=False, fatal=False, logger=None)
        if not r.succeeded:
            self.problem = short(r.full_output)
            return

        try:
            lines = r.output.strip().splitlines()
            if len(lines) != 3:
                self.problem = "introspection yielded %s lines instead of 3" % len(lines)
                return

            version, self.prefix, self.base_prefix = lines
            self.is_venv = self.prefix != self.base_prefix
            self.spec = depot.spec_from_text(version, exe)
            if not self.spec.version:
                self.problem = "unknown version"

        except Exception as e:  # pragma: no cover
            self.problem = "introspection error: %s" % short(e)


class UnknownPython(PythonInstallation):
    """Holds a problematic reference to an unknown python"""

    def __init__(self, depot, origin, path):
        super(UnknownPython, self).__init__(depot, origin, path, spec=depot.spec_from_text(path))
        self.problem = "not available"


class _Introspect(object):
    """Introspect a python installation via the built-in `_pv.py` script"""

    _pv = None

    @classmethod
    def get_pv(cls):
        if cls._pv is None:
            cls._pv = os.path.dirname(os.path.abspath(__file__))
            cls._pv = os.path.join(cls._pv, "_pv.py")

        return cls._pv
