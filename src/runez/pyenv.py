import os
import re
import sys
from collections import defaultdict

from runez.file import parent_folder
from runez.program import is_executable, run
from runez.system import _R, abort, flattened, joined, resolved_path, short, UNSET


CPYTHON = "cpython"
PYTHON_FAMILIES = (CPYTHON, "pypy", "conda")
R_SPEC = re.compile(r"^\s*((|py?|c?python|(ana|mini)?conda[23]?|pypy)\s*[:-]?)\s*([0-9]*)\.?([0-9]*)\.?([0-9]*)\s*$", re.IGNORECASE)
R_VERSION = re.compile(r"((\d+)((\.(\d+))*)((a|b|c|rc)(\d+))?(\.(dev|post|final)\.?(\d+))?).*")


def guess_family(text):
    """
    Args:
        text (str | None): Text to examine

    Returns:
        (str): Guessed python family from given 'text' (typically path to installation)
    """
    if text:
        for name in PYTHON_FAMILIES:
            if name in text:
                return name

    return CPYTHON


def pyenv_scanner(*locations):
    """Scan pyenv-style installation location(s)"""
    for location in flattened(locations, split=":", keep_empty=None):
        location = resolved_path(location)
        if location and os.path.isdir(location):
            count = 0
            pv = os.path.join(location, "versions")
            if os.path.isdir(pv):
                location = pv

            for fname in os.listdir(location):
                folder = os.path.join(location, fname)
                spec = PythonSpec(fname, folder)
                if spec.version:
                    exes = list(PythonDepot.python_exes_in_folder(folder))
                    if exes:
                        count += 1
                        problem = None

                    else:
                        problem = "invalid pyenv installation"

                    exes.append(folder)
                    yield PythonInstallation(exes[0], spec, equivalents=exes, problem=problem)

            _R.trace("Found %s pythons in %s" % (count, short(location)))


class PythonSpec(object):
    """
    Holds a canonical reference to a desired python installation
    Examples: 3, 3.9, py39, conda3.7.1, /usr/bin/python

    Scanned pythons have a full spec of the form: 'cpython:3.9.2'
    Desired pythons are typically partial (like: 'py39', turned into canonical 'cpython:3.9')
    `PythonDepot` can then search for pythons satisfying the partial specs given
    """

    def __init__(self, text, family=None):
        """
        Args:
            text (str | None): Text describing desired python
            family (str | None): Additional text to examine to determine python family
        """
        text = text.strip() if text else ""
        self.text = text
        self.version = None
        if text == "invoker":
            self.canonical = text
            self.family = guess_family(sys.version)
            self.version = Version(".".join(str(s) for s in sys.version_info[:3]))
            return

        self.family = guess_family(family or text)
        if _is_path(text):
            self.canonical = resolved_path(text)
            return

        m = R_SPEC.match(text)
        if not m:
            self.canonical = "?%s" % text  # Don't let arbitrary given text accidentally count as valid canonical
            return

        components = [s for s in (m.group(4), m.group(5), m.group(6)) if s]
        if len(components) == 1:
            components = [c for c in components[0]]  # Support notations of the form: "py37"

        if len(components) > 3:
            self.canonical = "?%s" % text  # Too many version components
            return

        if components:
            self.version = Version(".".join(components))

        self.canonical = "%s:%s" % (self.family, self.version or "")

    def __repr__(self):
        return short(self.canonical)

    def __hash__(self):
        return hash(self.canonical)

    def __eq__(self, other):
        return isinstance(other, PythonSpec) and self.canonical == other.canonical

    def __lt__(self, other):
        if isinstance(other, PythonSpec):
            if self.version is None or other.version is None:
                return bool(other.version)

            return self.version < other.version

    def satisfies(self, other, either_direction=False):
        """Does this spec satisfy 'other'?"""
        if isinstance(other, PythonSpec) and self.family == other.family:
            if self.canonical.startswith(other.canonical):
                return True

            if either_direction:
                return other.canonical.startswith(self.canonical)

    @staticmethod
    def represented_specs(specs, compact=None, delimiter=", ", depot=None, highlight=None):
        """
        Args:
            specs (PythonSpec | PythonInstallation | list | tuple | None): Specs to represent textually
            delimiter (str): Delimiter to use (if several specs provided)
            depot (PythonDepot | None): Optional depot to validate specs against
            highlight (PythonSpec | PythonInstallation | None): If provided, highlight corresponding in spec

        Returns:
            (str): Textual representation
        """
        if not specs:
            return ""

        result = []
        for spec in flattened(specs, keep_empty=None):
            python = depot and depot.find_python(spec)
            spec = getattr(spec, "spec", spec)  # Support passed-in `PythonInstallation` objects
            result.append(spec.represented(compact=compact, highlight=highlight, problem=python))

        return joined(result, delimiter=delimiter)

    def represented(self, compact=None, highlight=None, problem=None):
        """
        Args:
            compact (str | list | set | tuple | None): Show version only, if self.family is mentioned in `compact`
            highlight (PythonInstallation | PythonSpec | None): If provided, color in green if `self` matches `highlight` spec
            problem (PythonInstallation | str | bool | None): If true-ish, color in red

        Returns:
            (str): Textual representation of this spec
        """
        text = self
        if compact and self.family in compact:
            text = self.version

        problem = getattr(problem, "problem", problem)  # Support passed-in `PythonInstallation` objects
        if problem:
            text = _R._runez_module().red(text)

        elif self.satisfies(getattr(highlight, "spec", highlight), either_direction=True):
            text = _R._runez_module().green(text)

        return short(text)

    @classmethod
    def speccified(cls, values, strict=False):
        """
        Args:
            values (Iterable | None): Values to transform into a list of PythonSpec-s

        Returns:
            (list[PythonSpec] | None): Corresponding list of PythonSpec-s
        """
        if values:
            values = [x if isinstance(x, PythonSpec) else cls(x) for x in values if x]
            if strict:
                values = [x for x in values if x.version]

            return values


class PythonDepot(object):
    """
    Scan usual locations to discover python installations.
    2 types of location are scanned:
    - pyenv-like folders (very quick scan, scanned immediately)
    - PATH env var (slower scan, scanned as late as possible)

    Example usage:
        my_depot = PythonDepot(pyenv="~/.pyenv")
        p = my_depot.find_python("3.7")
    """

    from_path = None  # type: list[PythonInstallation]  # Installations from PATH env var
    invoker = None  # type: PythonInstallation  # The python installation (parent python, non-venv) that we're currently running under
    scanned = None  # type: list[PythonInstallation]  # Installations found by scanner
    scanned_prefixes = None  # type: set[str]  # Common path prefixes of installations yielded by scanners

    fatal = False  # abort() by default when a python could not be found?
    use_path = True  # Scan $PATH env var for python installations as well?
    _cache = None  # type: dict[str, PythonInstallation]

    def __init__(self, scanner=None, use_path=UNSET):
        """
        Args:
            scanner (typing.Iterator[PythonInstallation]): Scanner to use
            use_path (bool): Scan $PATH env var? (default: class attribute default)
        """
        if use_path is not UNSET:
            self.use_path = use_path

        self.from_path = None if self.use_path else []
        self._cache = {}
        self.scan(scanner)
        base_prefix = getattr(sys, "real_prefix", None) or getattr(sys, "base_prefix", sys.prefix)
        self.invoker = self._cache.get(base_prefix)
        if self.use_path and self.invoker is None:
            self.scan_path_env_var()
            self.invoker = self._cache.get(base_prefix)

        if self.invoker is None:
            self.invoker = self._find_invoker(base_prefix)

        self.invoker.is_invoker = True
        self._cache["invoker"] = self.invoker

    def __repr__(self):
        return "%s scanned%s" % (len(self.scanned), ", %s from PATH" % len(self.from_path) if self.from_path else "")

    @staticmethod
    def spec_from_text(text):
        """
        Args:
            text (str): Text to parse

        Returns:
            (PythonSpec): Associated spec
        """
        return PythonSpec(text)

    def find_python(self, spec, fatal=UNSET):
        """
        Args:
            spec (str | PythonSpec | PythonInstallation | None): Example: 3.7, py37, pypy3.7, conda3.7, /usr/bin/python
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log

        Returns:
            (PythonInstallation): Object representing python installation (may not be usable, see reported .problem)
        """
        if isinstance(spec, PythonInstallation):
            return spec

        if not isinstance(spec, PythonSpec):
            python = self._cache.get(spec)
            if python:
                return self._checked_pyinstall(python, fatal)

            spec = PythonSpec(spec)

        python = self._cache.get(spec.canonical)
        if python:
            return self._checked_pyinstall(python, fatal)

        if _is_path(spec.canonical):
            # Path reference: look it up and remember it "/"
            exe = self.resolved_python_exe(spec.canonical, major=sys.version_info[0])
            if not exe:
                python = PythonInstallation(spec.canonical, spec, problem="not an executable")
                return self._checked_pyinstall(python, fatal)

            python = self._cache.get(exe) or self._cache.get(os.path.realpath(exe))
            if python:
                return self._checked_pyinstall(python, fatal)

            python = self._python_from_path(exe)
            return self._checked_pyinstall(python, fatal)

        for python in self.scanned:
            if python.satisfies(spec):
                return python

        self.scan_path_env_var()
        for python in self.from_path:
            if python.satisfies(spec):
                return python

        if self.invoker.satisfies(spec):
            return self.invoker

        python = PythonInstallation(spec.text, spec, problem="not available")
        return self._checked_pyinstall(python, fatal)

    def scan(self, *scanners):
        self.scanned = []
        self.scanned_prefixes = set()
        for scanner in scanners:
            folders = []
            if scanner:
                for python in scanner:
                    self._register(python, self.scanned)
                    folder = python.folder
                    if folder:
                        folders.append(folder)

                prefix = os.path.commonprefix(folders)
                prefix = prefix and os.path.dirname(prefix)
                if prefix and len(prefix) > 2:
                    self.scanned_prefixes.add(prefix)

                self.scanned = sorted(self.scanned, reverse=True)

    def scan_path_env_var(self):
        """Ensure env vars locations are scanned
        Returns:
            (list[PythonInstallation] | None): Installations
        """
        if self.from_path is not None:
            return None

        self.from_path = []
        found = []
        real_paths = defaultdict(list)
        for folder in flattened(os.environ.get("PATH"), split=os.pathsep, keep_empty=None):
            for path in self.python_exes_in_folder(folder):
                real_path = os.path.realpath(path)
                if real_path not in self._cache:
                    real_paths[real_path].append(path)
                    if path != real_path:
                        real_paths[real_path].append(real_path)

        for real_path, paths in real_paths.items():
            python = self._python_from_path(paths[0], equivalents=paths)
            if python.problem:
                _R.trace("Ignoring invalid python in PATH: %s" % paths[0])

            else:
                self._register(python, self.from_path)
                found.append(python)

        _R.trace("Found %s pythons in $PATH" % (len(found)))
        return found

    @staticmethod
    def python_exes_in_folder(path, major=None):
        """
        Args:
            path (str): Path to python exe or folder with a python installation
            major (int | None): Optional, major version to search for

        Returns:
            Yields all python executable names
        """
        if path:
            path = resolved_path(path)
            if os.path.isdir(path):
                bin_folder = os.path.join(path, "bin")
                if os.path.isdir(bin_folder):
                    path = bin_folder

                names = ("python%s" % major, "python") if major else ("python", "python3", "python2")
                for name in names:
                    candidate = os.path.join(path, name)
                    if is_executable(candidate):
                        yield candidate

            elif is_executable(path):
                yield path

    def resolved_python_exe(self, path, major=None):
        """Find python executable from 'path'
        Args:
            path (str): Path to a bin/python, or a folder containing bin/python
            major (int | None): Optional, major version to search for

        Returns:
            (str): Full path to bin/python, if any
        """
        for exe in self.python_exes_in_folder(path, major=major):
            return exe

    def _find_invoker(self, base_prefix):
        info = PyInstallInfo(sys.version.partition(" ")[0], sys.prefix, base_prefix)
        equivalents = set()
        exe = None
        for path in self.python_exes_in_folder(info.base_prefix, major=info.version.major):
            equivalents.add(path)
            equivalents.add(os.path.realpath(path))
            if exe is None:
                exe = path

        if not exe:
            exe = os.path.realpath(sys.executable)

        for path in equivalents:
            python = self._cache.get(path)
            if python and not python.problem:
                return python

        spec = PythonSpec(info.version.text, exe)
        python = PythonInstallation(exe, spec, equivalents=equivalents)
        self._register(python, None)
        return python

    def representation(self, colored=True):
        """(str): Textual representation of available pythons"""
        scanned = [p.representation(colored=colored) for p in self.scanned]
        from_path = self.from_path and [p.representation(colored=colored) for p in self.from_path]
        return joined(
            scanned and ("\nAvailable pythons:", scanned),
            from_path and ("\nAvailable pythons from PATH:", "\n".join(from_path)),
            delimiter="\n",
            keep_empty=False
        ).strip()

    def _python_from_path(self, path, equivalents=None):
        """
        Args:
            path (str): Path to python executable
            equivalents (list | set | None): Additional equivalent paths

        Returns:
            (PythonInstallation): Corresponding python installation
        """
        info = _Introspect.scan_exe(path)
        if info.problem:
            return PythonInstallation(path, None, equivalents=equivalents, problem=info.problem)

        spec = PythonSpec(info.version.text, path)
        if info.sys_prefix != info.base_prefix:
            # We have a venv, return parent python
            exe = self.resolved_python_exe(info.base_prefix, major=info.version.major)
            python = self._cache.get(exe)
            if python:
                return python

            if not equivalents:
                equivalents = self.python_exes_in_folder(parent_folder(path), major=info.version.major)

            path = exe

        return PythonInstallation(path, spec, equivalents=equivalents)

    def _register(self, python, target):
        """
        Args:
            python (PythonInstallation): Python installation to register
            target (list | None): Where to keep a reference of registered python

        Returns:
            (int): 1 if registered (0 if python was invalid, or already known)
        """
        cached = False
        for p in python._equivalents:
            if p not in self._cache:
                self._cache[p] = python
                cached = True

        if cached and not python.problem and target is not None:
            target.append(python)
            return 1

        return 0

    def _checked_pyinstall(self, python, fatal):
        """Optionally abort if 'python' installation is not valid"""
        if python.problem:
            if fatal is UNSET:
                fatal = self.fatal

            if fatal:
                abort("Invalid python installation: %s" % python)

        return python


class Version(object):
    """
    Parse versions according to PEP-440, ordering for non pre-releases is well supported
    Pre-releases are partially supported, no complex combinations (such as ".post.dev") are paid attention to
    """

    def __init__(self, text, max_parts=4):
        """
        Args:
            text (str | None): Text to be parsed
            max_parts (int): Maximum number of parts (components) to consider version valid
        """
        self.text = text or ""
        self.components = None
        self.prerelease = None
        m = R_VERSION.match(self.text)
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
    def from_text(cls, text, strict=False):
        """
        Args:
            text (str | None): Text to be parsed
            strict (bool): If False, use first substring from 'text' that looks like a version number

        Returns:
            (Version | None): Parsed version, if valid
        """
        if text:
            if not strict and (not text[0].isdigit() or not text[-1].isdigit()):
                m = R_VERSION.search(text)
                if m:
                    text = m.group(1)

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
            if self.components is None or other.components is None:
                return bool(other.components)

            if self.components == other.components:
                if self.prerelease is None or other.prerelease is None:
                    return bool(other.prerelease)

                return self.prerelease < other.prerelease

            return self.components < other.components

    @property
    def is_valid(self):
        """Is this version valid?"""
        return self.components is not None

    @property
    def main(self):
        """(str): Main part of version (Major.minor.patch)"""
        if self.components:
            return "%s.%s.%s" % (self.major, self.minor, self.patch)

    @property
    def major(self):
        """(int): Major part of version"""
        return self.components and self.components[0]

    @property
    def minor(self):
        """(int): Minor part of version"""
        return self.components and self.components[1]

    @property
    def patch(self):
        """(int): Patch part of version"""
        return self.components and self.components[2]


class PythonInstallation(object):
    """Models a specific python installation"""

    executable = None  # type: str # Full path to python executable
    is_invoker = False  # Is this the python we're currently running under?
    short_name = None  # type: str # Used to textually represent this installation
    problem = None  # type: str # String describing a problem with this installation, if there is one
    spec = None  # type: PythonSpec # Corresponding spec

    _equivalents = None  # type: set[str] # Paths that are equivalent to this python installation

    def __init__(self, exe, spec, equivalents=None, problem=None):
        """
        Args:
            exe (str): Path to executable
            spec (PythonSpec | None): Associated spec
            equivalents (list | set | None): Optional equivalent identifiers for this installation
            problem (str | None): Problem with this installation, if any
        """
        self.executable = _simplified_python_path(exe)
        self.short_name = self.executable
        if "pyenv" in self.short_name:
            self.short_name = parent_folder(parent_folder(self.short_name))

        self.spec = spec
        self.problem = problem
        self._equivalents = {exe}
        if not problem:
            self._equivalents.add(os.path.realpath(exe))

        if self.executable != exe:
            self._equivalents.add(self.executable)
            if not problem:
                self._equivalents.add(os.path.realpath(self.executable))

        if equivalents:
            self._equivalents.update(equivalents)

    def __repr__(self):
        return self.representation(colored=False)

    def __hash__(self):
        return hash(self.executable)

    def __eq__(self, other):
        return isinstance(other, PythonInstallation) and self.executable == other.executable

    def __ne__(self, other):
        return not isinstance(other, PythonInstallation) or self.executable != other.executable

    def __lt__(self, other):
        if isinstance(other, PythonInstallation):
            if self.spec is None or other.spec is None:
                return bool(other.spec)

            return self.spec < other.spec

    @property
    def folder(self):
        """Folder where this python is installed, if installation is valid"""
        if self.executable and not self.problem:
            return os.path.dirname(self.executable)

    @property
    def major(self):
        """(int | None): Major python version, if any"""
        return self.spec and self.spec.version and self.spec.version.major

    @property
    def version(self):
        """(Version | None): Python version, if any"""
        return self.spec and self.spec.version

    def representation(self, colored=True):
        """(str): Colored textual representation of this python installation"""
        bold = dim = green = red = str
        if colored:
            rm = _R._runez_module()
            bold, dim, green, red = rm.bold, rm.dim, rm.green, rm.red

        note = [red(self.problem) if self.problem else self.spec]
        if self.is_invoker:
            note.append(green("invoker"))

        text = bold(short(self.short_name))
        if note:
            text += " [%s]" % ", ".join(dim(s) for s in note)

        return text

    def satisfies(self, spec):
        """
        Args:
            spec (PythonSpec): Spec expressed by user or configuration

        Returns:
            (bool): True if this python installation satisfies it
        """
        if not self.problem and self.spec:
            return self.spec.satisfies(spec)


class PyInstallInfo:
    """Information on a python installation, determined dynamically when needed"""

    def __init__(self, version=None, sys_prefix=None, base_prefix=None, problem=None):
        self.version = Version(version) if version else None
        self.sys_prefix = sys_prefix
        self.base_prefix = base_prefix
        if not problem and (not self.version or not self.version.is_valid):
            problem = "unknown version '%s'" % self.version

        self.problem = problem


class _Introspect(object):
    """Introspect a python installation via the built-in `_pv.py` script"""

    _pv = None

    @classmethod
    def scan_exe(cls, exe):
        """
        Args:
            exe (str): Path to python executable

        Returns:
            (PyInstallInfo): Extracted info
        """
        r = run(exe, cls.get_pv(), dryrun=False, fatal=False, logger=None)
        if not r.succeeded:
            return PyInstallInfo(problem=short(r.full_output))

        try:
            lines = r.output.strip().splitlines()
            if len(lines) != 3:
                return PyInstallInfo(problem="introspection yielded %s lines instead of 3" % len(lines))

            version, sys_prefix, base_prefix = lines
            return PyInstallInfo(version, sys_prefix, base_prefix)

        except Exception as e:  # pragma: no cover
            return PyInstallInfo(problem="introspection error: %s" % short(e))

    @classmethod
    def get_pv(cls):
        if cls._pv is None:
            cls._pv = os.path.join(parent_folder(__file__), "_pv.py")

        return cls._pv


def _is_path(text):
    if text:
        return text.startswith("~") or text.startswith(".") or "/" in text


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
