import logging
import os
import re
import sys
from collections import defaultdict

from runez.program import is_executable, run
from runez.system import _R, abort, cached_property, flattened, resolved_path, short, UNSET


CPYTHON_NAMES = ["python", "", "p", "py", "cpython"]
DEFAULT_FAMILY = CPYTHON_NAMES[-1]
FAMILIES = ["conda", "pypy"]
R_SPEC = re.compile(r"^\s*((|py?|c?python|(ana|mini)?conda[23]?|pypy)\s*[:-]?)\s*([0-9]*)\.?([0-9]*)\.?([0-9]*)\s*$", re.IGNORECASE)
R_VERSION = re.compile(r"^((\d+)((\.(\d+))*)((a|b|c|rc)(\d+))?(\.(dev|post|final)\.?(\d+))?).*$")
LOG = logging.getLogger(__name__)


class PythonSpec(object):
    """
    Holds a canonical reference to a desired python installation
    Examples: 3, 3.9, py39, conda3.7.1, /usr/bin/python
    """

    version = None  # type: Version

    def __init__(self, text, family=None):
        """
        Args:
            text (str | None): Text describing desired python
            family (str | None): Pre-determined python family, if any
        """
        text = text.strip() if text else ""
        self.given_name = None
        self.text = text
        self.family = family or self.guess_family(text)
        if text in CPYTHON_NAMES:
            self.given_name = CPYTHON_NAMES[0]
            self.canonical = "%s" % self.family
            return

        if os.path.isabs(text) or text.startswith("~") or "/" in text:
            self.canonical = resolved_path(text)
            return

        self.canonical = "?%s" % text  # Don't let arbitrary given text accidentally count as valid canonical
        m = R_SPEC.match(text)
        if not m:
            return

        self.given_name = m.group(2).lower()
        components = [s for s in (m.group(4), m.group(5), m.group(6)) if s]
        if len(components) == 1:
            components = [c for c in components[0]]  # Support notation of the form: py37

        if components and len(components) <= 3:
            self.version = Version(".".join(components))
            self.canonical = "%s:%s" % (self.family, self.version.text)
            if self.given_name in CPYTHON_NAMES:
                self.given_name = CPYTHON_NAMES[0]

    def __repr__(self):
        return short(self.canonical)

    def __eq__(self, other):
        return isinstance(other, PythonSpec) and self.canonical == other.canonical

    def __lt__(self, other):
        if isinstance(other, PythonSpec):
            if self.family == other.family:
                return self.version and other.version and self.version < other.version

            if self.family != DEFAULT_FAMILY:
                return other.family == DEFAULT_FAMILY or self.family < other.family

    @staticmethod
    def guess_family(text):
        """Guessed python familty from given 'text' (typically path to installation)"""
        for name in FAMILIES:
            if name in text:
                return name

        return DEFAULT_FAMILY


class PythonDepot(object):
    """Holds a reference to all discovered python installations so far, designed to be used as singleton via DEPOT"""

    # Paths to scan in a deferred fashion (as late as possible), in PythonDepot.find_python()
    DEFAULT_DEFERRED = ["$PATH"]
    EXE_NAMES = ("python", "python3", "python2")

    def __init__(self):
        self.invalid = []  # type: list[PythonInstallation]  # Invalid python installations found
        self.available = []  # type: list[PythonInstallation]  # Available installations (used to find pythons by spec)
        self.deferred = list(self.DEFAULT_DEFERRED)
        self._cache = {}  # type: dict[str, PythonInstallation]

    def reset(self):
        """Reset scanned python installation references, calls this if you'd like to rescan"""
        self.invalid = []
        self.available = []
        self.deferred = list(self.DEFAULT_DEFERRED)
        self._cache = {}

    @cached_property
    def invoker(self):
        """Python we're currently running under"""
        return InvokerPython()

    def _cached_equivalents(self, python):
        count = 0
        for p in python.equivalent:
            if p not in self._cache:
                self._cache[p] = python
                count += 1

        return count

    def _register(self, python):
        count = self._cached_equivalents(python)
        if count:
            if python.problem:
                self.invalid.append(python)
                return 0

            self.available.append(python)

        return count

    def register_invoker(self):
        """Use invoker python"""
        return self._register(self.invoker)

    def register_deferred(self, *paths):
        """Add 'paths' to self.deferred, to be examined as late as possible. when/if no python can be found in registered places so far"""
        for path in paths:
            if path and path not in self._cache and path not in self.deferred:
                self.deferred.append(path)

    def scan_pyenv(self, path, logger=UNSET):
        """Find pythons from pyenv-style installation folders

        Args:
            path (str | list[str]): Folder(s) to scan
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
        """
        available = []
        paths = flattened(path, split=":", keep_empty=None)
        for path in paths:
            path = resolved_path(path)
            if not path or not os.path.isdir(path):
                _R.hlog(logger, "Folder '%s' does not exist, ignoring pyenv location" % short(path))
                continue

            pv = os.path.join(path, "versions")
            if os.path.isdir(pv):
                path = pv

            for fname in os.listdir(path):
                spec = PythonSpec(fname)
                if spec.version:
                    python = PythonPyenvInstallation(os.path.join(path, fname), spec)
                    available.append(python)

        available = sorted(available, reverse=True)
        for p in available:
            self._register(p)

        return available

    def scan_path(self, env_var="PATH"):
        """Register pythons from PATH-like env var ('os.pathsep'-separated)"""
        available = []
        explored = set()
        for folder in flattened(os.environ.get(env_var), split=os.pathsep, keep_empty=None):
            folder = resolved_path(folder)
            if folder not in explored:
                explored.add(folder)
                real_paths = defaultdict(list)
                for name in self.EXE_NAMES:
                    path = os.path.join(folder, name)
                    if path not in self._cache and is_executable(path):
                        real_path = os.path.realpath(path)
                        if real_path not in self._cache:
                            real_paths[real_path].append(path)

                for k, paths in real_paths.items():
                    python = PythonFromPath(paths[0])
                    for path in paths:
                        python._add_equivalent(path, add_realpath=False)

                    if self._register(python):
                        available.append(python)

        return available

    def find_python(self, spec, fatal=False, logger=UNSET):
        """
        Args:
            spec (str | PythonSpec | None): Example: 3.7, py37, pypy3.7, conda3.7, /usr/bin/python
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter

        Returns:
            (PythonInstallation | None): Object representing python installation (may not be usable, see reported .problem)
        """
        if not isinstance(spec, PythonSpec):
            if spec == self.invoker.spec.given_name:
                return self.invoker

            spec = PythonSpec(spec)

        if not self._cache:
            self.register_invoker()

        python = self._cache.get(spec.canonical)
        if python:
            return python

        if spec.canonical and os.path.isabs(spec.canonical):
            python = PythonFromPath(spec)  # Absolute path: look it up and remember it (if valid)
            if not python.problem:
                if self._register(python):
                    _R.hlog(logger, "Cached new python installation %s" % python)

            return self._checked_pyinstall(python, fatal)

        for python in self.available:
            if python.satisfies(spec):
                return python

        if self.deferred:
            python = self.scan_deferred(logger=logger, spec=spec)
            if python:
                return python

        return self._checked_pyinstall(UnknownPython(spec), fatal)

    @classmethod
    def python_from_path(cls, path):
        """Find python executable from 'path'"""
        if path and os.path.isdir(path):
            folder = path
            bin_folder = os.path.join(folder, "bin")
            if os.path.isdir(bin_folder):
                folder = bin_folder

            for name in cls.EXE_NAMES:
                candidate = os.path.join(folder, name)
                if is_executable(candidate):
                    return candidate

        return path

    def scan_deferred(self, logger=UNSET, spec=None):
        """Scan remaining 'self.deferred' to find more potential python installations
        Args:
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            spec (str | PythonSpec | None): Example: 3.7, py37, pypy3.7, conda3.7, /usr/bin/python

        Returns:
            (PythonInstallation | list | None): Python installation (if 'spec' provided), list of all found installations otherwise
        """
        cumulatively_added = []
        while self.deferred:
            path = self.deferred.pop(0)
            if not path:
                continue

            if path.startswith("$"):
                added = self.scan_path(path[1:])
                if added:
                    cumulatively_added.extend(added)
                    _R.hlog(logger, "Found %s deferred pythons from %s: %s" % (len(added), path, added))
                    if spec:
                        for python in added:
                            if python.satisfies(spec):
                                return python

            elif is_executable(path):
                python = PythonFromPath(path)
                if self._register(python):
                    cumulatively_added.append(python)
                    _R.hlog(logger, "Found deferred python: %s" % (python))
                    if spec and python.satisfies(spec):
                        return python

        return cumulatively_added if spec is None else None

    @staticmethod
    def _checked_pyinstall(python, fatal):
        """Optionally abort if 'python' installation is not valid"""
        if fatal and python.problem:
            abort("Invalid python installation: %s" % python)

        return python


DEPOT = PythonDepot()


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

                return bool(other.prerelease)

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
    is_venv = None  # type: bool # Is this python installation a venv?
    problem = None  # type: str # String describing a problem with this installation, if there is one
    spec = None  # type: PythonSpec # Corresponding spec

    def __repr__(self):
        return "%s [%s]" % (short(self.executable), self.problem or self.spec.canonical)

    def __eq__(self, other):
        return isinstance(other, PythonInstallation) and self.executable == other.executable

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        if isinstance(other, PythonInstallation):
            return self.spec < other.spec

    @property
    def major(self):
        """Major python version, if any"""
        if self.spec and self.spec.version:
            return self.spec.version.major

    def colored_representation(self):
        """Colored textual representation of this python installation"""
        color = _R._runez_module().red if self.problem else _R._runez_module().dim
        note = "[%s]" % (self.problem or self.spec.canonical)
        if self.spec and self.spec.given_name and self.spec.given_name != CPYTHON_NAMES[0]:
            note += _R._runez_module().orange(_R._runez_module().dim(" [%s]" % self.spec.given_name))

        return "%s %s" % (_R._runez_module().bold(short(self.executable)), color(note))

    def satisfies(self, spec):
        """
        Args:
            spec (PythonSpec): Spec expressed by user or configuration

        Returns:
            (bool): True if this python installation satisfies it
        """
        if spec.canonical in self.equivalent:
            return True

        if self.problem:
            return False

        return self.spec.canonical.startswith(spec.canonical)

    def _add_equivalent(self, path, add_realpath=True):
        if self.equivalent is None:
            self.equivalent = set()

        if path and path not in self.equivalent:
            self.equivalent.add(path)
            if add_realpath:
                self.equivalent.add(os.path.realpath(path))


class InvokerPython(PythonInstallation):
    """Python we're currently running under"""

    def __init__(self):
        family = getattr(sys, "implementation", None)
        if family:
            family = getattr(family, "name", None)

        self.spec = PythonSpec(".".join(str(c) for c in sys.version_info[:3]), family=family)
        self.spec.given_name = "invoker"
        prefix = getattr(sys, "real_prefix", None)  # old py2 case
        if not prefix:
            prefix = getattr(sys, "base_prefix", sys.prefix)

        if not prefix:
            parent = sys.executable

        else:
            parent = os.path.join(prefix, "bin/python%s" % self.spec.version.major)
            if not is_executable(parent):
                parent = os.path.join(prefix, "bin/python")

        self.executable = self._simplified_python_path(parent)
        self._add_equivalent(self.executable)
        self._add_equivalent(parent)
        self._add_equivalent(self.spec.given_name, add_realpath=False)

    @staticmethod
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


class PythonPyenvInstallation(PythonInstallation):
    """Models a pyenv-style installation"""

    def __init__(self, folder, spec):
        self.spec = spec
        for name in PythonDepot.EXE_NAMES:
            exe = os.path.join(folder, "bin", name)
            if is_executable(exe):
                self._add_equivalent(exe)
                if self.executable is None:
                    self.executable = exe

        if not self.executable:
            self.executable = os.path.join(folder, "bin", CPYTHON_NAMES[0])
            self._add_equivalent(self.executable)
            self.problem = "invalid pyenv installation"


class PythonFromPath(PythonInstallation):
    """Python installation from a specific local path"""

    def __init__(self, path):
        """
        Args:
            path (str | PythonSpec): Absolute path to python executable
        """
        if isinstance(path, PythonSpec):
            self.spec = path
            path = PythonDepot.python_from_path(path.canonical)

        self.executable = path
        self.base_prefix = None
        self.prefix = None
        self._add_equivalent(path, add_realpath=False)
        pv = _Introspect.get_pv()
        r = run(path, pv, dryrun=False, fatal=False, logger=None)
        if not r.succeeded:
            self.problem = "can't be introspected: %s" % short(r.full_output)
            return

        try:
            lines = r.output.strip().splitlines()
            version, self.prefix, self.base_prefix = lines
            self.is_venv = self.prefix != self.base_prefix
            version, _, family_text = version.partition(" ")
            self.spec = PythonSpec(version, PythonSpec.guess_family(family_text))
            if not self.spec.version:
                self.problem = "unknown version"

        except Exception as e:
            self.problem = "can't be introspected: %s" % short(e)


class UnknownPython(PythonInstallation):
    """Holds a problematic reference to an unknown python"""

    def __init__(self, spec):
        """
        Args:
            spec (str | PythonSpec): Given (invalid) spec
        """
        if not isinstance(spec, PythonSpec):
            spec = PythonSpec(spec)

        self.spec = spec
        self.executable = spec.text or spec.canonical
        self._add_equivalent(self.executable, add_realpath=False)
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
