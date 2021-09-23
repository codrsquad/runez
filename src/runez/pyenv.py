import json
import os
import re
import sys
from collections import defaultdict

from runez.file import ls_dir, parent_folder, to_path
from runez.http import RestClient, urljoin
from runez.program import is_executable, run
from runez.system import _R, abort, cached_property, flattened, joined, ltattr, resolved_path, short, stringified, UNSET


CPYTHON = "cpython"
PYTHON_FAMILIES = (CPYTHON, "pypy", "conda")
R_SPEC = re.compile(r"^\s*((|py?|c?python|(ana|mini)?conda[23]?|pypy)\s*[:-]?)\s*(\d*)\.?(\d*)\.?(\d*)\s*(\+?)$", re.IGNORECASE)
R_VERSION = re.compile(r"v?((\d+!)?(\d+)((\.(\d+))*)((a|b|c|rc)(\d+))?(\.(dev|post|final)\.?(\d+))?(\+[\w.-]*)?).*")


def get_current_version(components=3):
    return Version(".".join(str(s) for s in sys.version_info[:components]))


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


class ArtifactInfo:
    """Info extracted from a typical python build artifact basename"""

    def __init__(self, basename, package_name, version, is_wheel=False, source=None, tags=None, wheel_build_number=None):
        """
        Args:
            basename (str): Basename of artifact
            package_name (str): Package name, may not be completely standard
            version (Version): Package version
            is_wheel (bool): Is this artifact a wheel?
            source: Optional arbitrary object to track provenance of ArtifactInfo
            tags (str | None): Wheel tags, if any
            wheel_build_number (str | None): Wheel build number, if any
        """
        self.basename = basename
        self.package_name = package_name
        self.version = version
        self.is_wheel = is_wheel
        self.source = source
        self.tags = tags
        self.wheel_build_number = wheel_build_number
        self.pypi_name = PypiStd.std_package_name(package_name)
        self.relative_url = "%s/%s" % (self.pypi_name, basename)

    @classmethod
    def from_basename(cls, basename, source=None):
        """
        Args:
            basename (str): Basename to parse
            source: Optional arbitrary object to track provenance of ArtifactInfo

        Returns:
            (ArtifactInfo | None): Parsed artifact info, if any
        """
        is_wheel = wheel_build_number = tags = None
        m = PypiStd.RX_SDIST.match(basename)
        if not m:
            m = PypiStd.RX_WHEEL.match(basename)
            if not m:
                return None

            wheel_build_number = m.group(4)
            tags = m.group(5)
            is_wheel = True

        # RX_SDIST and RX_WHEEL both yield package_name and version as match groups 1 and 2
        version = Version(m.group(2))
        return cls(basename, m.group(1), version, is_wheel=is_wheel, source=source, tags=tags, wheel_build_number=wheel_build_number)

    def __repr__(self):
        return self.relative_url or self.basename

    def __eq__(self, other):
        return isinstance(other, ArtifactInfo) and self.basename == other.basename

    def __lt__(self, other):
        """Ordered by source, then pypi_name, then version, then category"""
        return ltattr(self, other, "source", "pypi_name", "version", "category", t=ArtifactInfo)

    @property
    def category(self):
        return "wheel" if self.is_wheel else "source distribution"

    @property
    def is_dirty(self):
        return not self.version or "dirty" in self.version.text


class PypiStd:
    """
    Check/standardize pypi package names
    More strict than actual pypi (for example: names starting with a number are not considered value)
    """

    RX_ACCEPTABLE_PACKAGE_NAME = re.compile(r"^[a-z][\w.-]*[a-z\d]$", re.IGNORECASE)
    RR_PYPI = re.compile(r"([^a-z\d-]+|--+)", re.IGNORECASE)
    RR_WHEEL = re.compile(r"[^a-z\d.]+", re.IGNORECASE)

    RX_HREF = re.compile(r'href=".+/([^/#]+\.(tar\.gz|whl))#', re.IGNORECASE)
    RX_SDIST = re.compile(r"^([a-z][\w.-]*[a-z\d])-(\d[\w.!+-]*)\.tar\.gz$", re.IGNORECASE)
    RX_WHEEL = re.compile(r"^([a-z][\w.]*[a-z\d])-(\d[\w.!+]*)(-(\d[\w.]*))?-(.*)\.whl$", re.IGNORECASE)

    DEFAULT_PYPI_URL = "https://pypi.org/pypi/{name}/json"
    _pypi_client = None

    @classmethod
    def is_acceptable(cls, name):
        """Is 'name' an acceptable pypi package name?"""
        return bool(isinstance(name, str) and name != "UNKNOWN" and cls.RX_ACCEPTABLE_PACKAGE_NAME.match(name))

    @classmethod
    def std_package_name(cls, name):
        """Standardized pypi package name, single dashes and alpha numeric chars allowed only"""
        if cls.is_acceptable(name):
            dashed = cls.RR_PYPI.sub("-", name).lower()
            return cls.RR_PYPI.sub("-", dashed)  # 2nd pass to ensure no `--` remains

    @classmethod
    def std_wheel_basename(cls, name):
        """Standardized wheel file base name, single underscores, dots and alpha numeric chars only"""
        if cls.is_acceptable(name):
            return cls.RR_WHEEL.sub("_", name)

    @classmethod
    def default_pypi_client(cls):
        """
        Returns:
            (RestClient): Default client to use to query pypi
        """
        if cls._pypi_client is None:
            cls._pypi_client = RestClient()

        return cls._pypi_client

    @classmethod
    def pypi_response(cls, package_name, client=None, index=None, fatal=False, logger=False):
        """See https://warehouse.pypa.io/api-reference/json/
        Args:
            package_name (str): Pypi package name
            client (RestClient | None): Optional custom pypi client to use
            index (str | None): Optional custom pypi index url
            fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

        Returns:
            (dict | str | None): Dict if we queried actual REST endpoint, html text otherwise (legacy pypi simple)
        """
        pypi_name = cls.std_package_name(package_name)
        if not pypi_name:
            return None

        if client:
            if not index:
                index = client.base_url

        else:
            client = cls.default_pypi_client()

        if not index:
            index = cls.DEFAULT_PYPI_URL

        if "{name}" in index:
            url = index.format(name=pypi_name)

        else:
            url = urljoin(index, "%s/" % pypi_name)

        r = client.get_response(url, fatal=fatal, logger=logger)
        if r and r.ok:
            text = (r.text or "").strip()
            if text.startswith("{"):
                return json.loads(text)

            return text

    @classmethod
    def latest_pypi_version(cls, package_name, client=None, index=None, include_prerelease=False, fatal=False, logger=False):
        """
        Args:
            package_name (str): Pypi package name
            client (RestClient | None): Optional custom pypi client to use
            index (str | None): Optional custom pypi index url
            include_prerelease (bool): If True, include pre-releases
            fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

        Returns:
            (Version | None): Latest version, if any
        """
        response = cls.pypi_response(package_name, client=client, index=index, fatal=fatal, logger=logger)
        if response:
            if isinstance(response, dict):
                info = response.get("info")
                if isinstance(info, dict) and not info.get("yanked"):  # Not sure if this can ever happen
                    version = Version(info.get("version"))
                    if version.is_valid and (include_prerelease or not version.prerelease):
                        return version

                versions = sorted(x.version for x in cls._versions_from_pypi(response.get("releases")))

            else:
                versions = sorted(i.version for i in cls._parsed_legacy_html(response))

            if not include_prerelease:
                candidates = [v for v in versions if v.is_valid and not v.prerelease]
                if candidates:
                    versions = candidates

            if versions:
                return versions[-1]

    @classmethod
    def ls_pypi(cls, package_name, client=None, index=None, source=None, fatal=False, logger=False):
        """
        Args:
            package_name (str): Pypi package name
            client (RestClient | None): Optional custom pypi client to use
            index (str | None): Optional custom pypi index url
            source: Optional arbitrary object to track provenance of ArtifactInfo
            fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

        Returns:
            (list[ArtifactInfo] | None): Artifacts reported by pypi mirror
        """
        response = cls.pypi_response(package_name, client=client, index=index, fatal=fatal, logger=logger)
        if isinstance(response, dict):
            yield from cls._versions_from_pypi(response.get("releases"), source=source)

        elif response:
            yield from cls._parsed_legacy_html(response, source=source)

    @classmethod
    def _versions_from_pypi(cls, releases, source=None):
        if isinstance(releases, dict):
            for v, infos in releases.items():
                for info in infos:
                    if not info.get("yanked"):
                        info = ArtifactInfo.from_basename(info.get("filename"), source=source)
                        if info:
                            yield info

    @classmethod
    def _parsed_legacy_html(cls, text, source=None):
        """
        Args:
            text (str): Text as received from a legacy pypi server
            source: Optional arbitrary object to track provenance of ArtifactInfo

        Yields:
            (ArtifactInfo): Extracted information
        """
        if text:
            lines = text.strip().splitlines()
            if lines and "does not exist" not in lines[0]:
                for line in lines:
                    m = cls.RX_HREF.search(line)
                    if m:
                        info = ArtifactInfo.from_basename(m.group(1), source=source)
                        if info:
                            yield info


class PythonSpec:
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
            text: Text describing desired python (note: an empty or None `text` will yield a generic "cpython:" spec)
            family (str | None): Additional text to examine to determine python family
        """
        text = stringified(text, none="").strip()
        self.text = text
        self.version = None
        self.is_min_spec = ""
        if text == "invoker":
            self.canonical = text
            self.family = guess_family(sys.version)
            self.version = get_current_version()
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
        min_ver_marker = m.group(7)
        if len(components) == 1:
            components = [c for c in components[0]]  # Support notations of the form: "py37"

        if len(components) > 3 or (not components and min_ver_marker):
            self.canonical = "?%s" % text  # Too many version components, or '+' marker without actual version
            return

        if components:
            self.version = Version(".".join(components))

        if min_ver_marker:
            self.is_min_spec = "+"

        self.canonical = "%s:%s%s" % (self.family, self.version or "", self.is_min_spec)

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

    def satisfies(self, other):
        """Does this spec satisfy 'other'?"""
        if isinstance(other, PythonSpec) and self.family == other.family:
            if other.is_min_spec:
                return self.version >= other.version

            if self.canonical.startswith(other.canonical):
                return True

    def represented(self, color=None, compact=CPYTHON):
        """
        Args:
            color (callable | None): Optional color to use
            compact (str | list | set | tuple | bool | None): Show version only, if self.family is mentioned in `compact`

        Returns:
            (str): Textual representation of this spec
        """
        value = self
        if compact and self.version and (compact is True or self.family in compact):
            value = self.version

        return _R.colored(str(value), color)

    @classmethod
    def speccified(cls, values, strict=False):
        """
        Args:
            values (Iterable | None): Values to transform into a list of PythonSpec-s

        Returns:
            (list[PythonSpec]): Corresponding list of PythonSpec-s
        """
        values = flattened(values, split=",", transform=PythonSpec.to_spec)
        if strict:
            values = [x for x in values if x.version]

        return values

    @staticmethod
    def to_spec(value):
        """
        Args:
            value: Value to be converted into a PythonSpec() object

        Returns:
            (PythonSpec): Parsed spec from given object
        """
        if isinstance(value, PythonSpec):
            return value

        return PythonSpec(value)


class PythonInstallationScanner:
    """
    Scan python installations
    Default implementation scans a pyenv-like location, descendants of this class can redefine this
    """

    scanner_name = "portable python"

    def __init__(self, location, regex=None, version_group=1):
        """
        Args:
            location (pathlib.Path | str | None): Location on disk to examine
            regex: Optional regex to validate basename-s of folders under location scanned
            version_group (int): Matched group in regex that corresponds to version
        """
        self.location = to_path(location)
        self.regex = regex or re.compile(r"^.*?(\d+\.\d+\.\d+)$")
        self.version_group = version_group

    def __repr__(self):
        return "%s [%s]" % (self.scanner_name, short(self.location))

    def spec_from_path(self, path, family=None):
        if path.is_dir():
            m = self.regex.match(path.name)
            if m:
                spec = PythonSpec(m.group(self.version_group), family=family)
                if spec.version:
                    return spec

    def python_from_path(self, path):
        if path:
            short_name = str(path)
            spec = self.spec_from_path(path, family=short_name)
            if spec:
                exes = list(PythonDepot.python_exes_in_folder(path))
                problem = None if exes else "invalid python installation"
                exes.append(resolved_path(path))
                return PythonInstallation(exes[0], spec, equivalents=exes, problem=problem, short_name=short_name)

    def resolved_location(self):
        location = self.location
        if location and location.is_dir():
            pv = location / "versions"
            if pv.is_dir():
                location = pv

            return location

    def scan(self):
        """
        Yields:
            (PythonInstallation): Found python installations
        """
        for child in ls_dir(self.resolved_location()):
            if child.is_dir() and not child.is_symlink():
                yield self.python_from_path(child)

    def unknown_python(self, spec):
        """
        Args:
            spec (PythonSpec): Called when find_python() was given the spec of an unknown (not scanned) python

        Returns:
            (PythonInstallation): Object to represent python with 'spec', if this scanner can provide one
        """


class PythonDepot:
    """
    Scan usual locations to discover python installations.
    2 types of location are scanned:
    - pyenv-like folders (very quick scan, scanned immediately)
    - PATH env var (slower scan, scanned as late as possible)

    Example usage:
        my_scanner = PythonInstallationScanner("~/.pyenv")
        my_depot = PythonDepot(scanner=my_scanner)
        p = my_depot.find_python("3.7")
    """

    from_path = None  # type: list[PythonInstallation]  # Installations from PATH env var
    invoker = None  # type: PythonInstallation  # The python installation (parent python, non-venv) that we're currently running under
    scanned = None  # type: list[PythonInstallation]  # Installations found by scanner

    use_path = True  # Scan $PATH env var for python installations as well?
    _cache = None  # type: dict[str, PythonInstallation]

    def __init__(self, scanner=None, use_path=UNSET, logger=False):
        """
        Args:
            scanner (PythonInstallationScanner | None): Optional additional scanner to use
            use_path (bool): Scan $PATH env var? (default: class attribute default)
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
        """
        self.py_scanner = scanner
        if use_path is not UNSET:
            self.use_path = use_path

        self.logger = logger
        self.from_path = None if self.use_path else []
        self._cache = {}
        self.scanned = []
        scanned = scanner.scan() if scanner else None
        if scanned:
            for python in scanned:
                if python:
                    if python.problem:
                        _R.hlog(self.logger, "Ignoring invalid python in %s: %s" % (self, python))

                    else:
                        self._register(python, self.scanned)

            self.scanned = sorted(self.scanned, reverse=True)
            _R.hlog(self.logger, "Found %s pythons in %s" % (len(self.scanned), scanner))

        self.invoker = self._cache.get(sys.base_prefix)
        if self.use_path and self.invoker is None:
            self.scan_path_env_var()
            self.invoker = self._cache.get(sys.base_prefix)

        if self.invoker is None:
            self.invoker = self._find_invoker()

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
        return PythonSpec.to_spec(text)

    def find_python(self, spec, fatal=False, logger=False):
        """
        Args:
            spec (str | PythonSpec | PythonInstallation | None): Example: 3.7, py37, pypy3.7, conda3.7, /usr/bin/python
            fatal (type | bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

        Returns:
            (PythonInstallation): Object representing python installation (may not be usable, see reported .problem)
        """
        if isinstance(spec, PythonInstallation):
            return spec

        if not isinstance(spec, PythonSpec):
            python = self._cache.get(spec)
            if python:
                return self._checked_pyinstall(python, fatal, logger)

            spec = PythonSpec(spec)

        python = self._cache.get(spec.canonical)
        if python:
            return self._checked_pyinstall(python, fatal, logger)

        if _is_path(spec.canonical):
            # Path reference: look it up and remember it "/"
            exe = self.resolved_python_exe(spec.canonical, version=get_current_version(components=2))
            if not exe:
                python = PythonInstallation(spec.canonical, spec, problem="not an executable")
                return self._checked_pyinstall(python, fatal, logger)

            python = self._cache.get(exe) or self._cache.get(os.path.realpath(exe))
            if python:
                return self._checked_pyinstall(python, fatal, logger)

            python = self._python_from_path(exe)
            return self._checked_pyinstall(python, fatal, logger)

        for python in self.scanned:
            if python.satisfies(spec):
                return python

        self.scan_path_env_var()
        for python in self.from_path:
            if python.satisfies(spec):
                return python

        if self.invoker.satisfies(spec):
            return self.invoker

        python = None
        if self.py_scanner:
            python = self.py_scanner.unknown_python(spec)
            if python and not python.problem:
                if self._register(python, self.scanned):
                    self.scanned = sorted(self.scanned, reverse=True)

        if python is None:
            python = PythonInstallation(spec.text, spec, problem="not available")

        return self._checked_pyinstall(python, fatal, logger)

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
        for folder in flattened(os.environ.get("PATH"), split=os.pathsep):
            for path in self.python_exes_in_folder(folder):
                real_path = os.path.realpath(path)
                if real_path not in self._cache:
                    real_paths[real_path].append(path)
                    if path != real_path:
                        real_paths[real_path].append(real_path)

        for real_path, paths in real_paths.items():
            python = self._python_from_path(paths[0], equivalents=paths)
            if python.problem:
                _R.hlog(self.logger, "Ignoring invalid python in PATH: %s" % paths[0])

            else:
                self._register(python, self.from_path)
                found.append(python)

        _R.hlog(self.logger, "Found %s pythons in $PATH" % (len(found)))
        return found

    @staticmethod
    def python_exes_in_folder(path, version=None):
        """
        Args:
            path (pathlib.Path | str): Path to python exe or folder with a python installation
            version (Version | None): Optional, major/minor version to search for

        Returns:
            Yields all python executable names
        """
        if path:
            path = resolved_path(path)
            if os.path.isdir(path):
                bin_folder = os.path.join(path, "bin")
                if os.path.isdir(bin_folder):
                    path = bin_folder

                candidates = []
                if version and version.given_components:
                    if len(version.given_components) > 1:
                        candidates.append("python%s.%s" % (version.major, version.minor))

                    candidates.append("python%s" % version.major)

                else:
                    candidates.append("python3")

                candidates.append("python")
                for name in candidates:
                    candidate = os.path.join(path, name)
                    if is_executable(candidate):
                        yield candidate

            elif is_executable(path):
                yield path

    def resolved_python_exe(self, path, version=None):
        """Find python executable from 'path'
        Args:
            path (str): Path to a bin/python, or a folder containing bin/python
            version (Version | None): Optional, major/minor version to search for

        Returns:
            (str): Full path to bin/python, if any
        """
        for exe in self.python_exes_in_folder(path, version=version):
            return exe

    def _find_invoker(self):
        version = get_current_version()
        equivalents = set()
        exe = None
        for path in self.python_exes_in_folder(sys.base_prefix, version=version):
            real_path = os.path.realpath(path)
            if exe is None:
                exe = real_path
                equivalents.add(exe)
                equivalents.add(path)

            elif real_path == exe:
                equivalents.add(path)

        if not exe:
            exe = os.path.realpath(sys.executable)

        for path in equivalents:
            python = self._cache.get(path)
            if python and not python.problem:
                return python

        spec = PythonSpec(version.text, exe)
        python = PythonInstallation(exe, spec, equivalents=equivalents)
        self._register(python, None)
        return python

    def representation(self):
        """(str): Textual representation of available pythons"""
        header = None
        if self.py_scanner and self.py_scanner.scanner_name:
            header = "Installed %s:" if self.scanned else _R.colored("No %s installed", "orange")
            header = header % self.py_scanner.scanner_name

        from_path = self.from_path
        if from_path:
            from_path = joined("\nAvailable pythons from PATH:", from_path, delimiter="\n")

        return joined(header, self.scanned, from_path, delimiter="\n")

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
            exe = self.resolved_python_exe(info.base_prefix, version=info.version)
            python = self._cache.get(exe)
            if python:
                return python

            if not equivalents:
                equivalents = self.python_exes_in_folder(parent_folder(path), version=info.version)

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

        if cached and not python.problem and target is not None and python not in target:
            target.append(python)
            return 1

        return 0

    def _checked_pyinstall(self, python, fatal, logger):
        """Optionally abort if 'python' installation is not valid"""
        if python.problem and fatal:
            abort("Invalid python installation: %s" % python, fatal=fatal, logger=logger)

        return python


class Version:
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
        self.components = None  # tuple of components with exactly 'max_parts', auto-filled with zeros
        self.given_components = None  # Components as given by 'text'
        self.epoch = 0
        self.local_part = None
        self.prerelease = None
        self.suffix = None
        m = R_VERSION.match(self.text)
        if not m:
            return

        self.text, epoch, major, main_part, pre, pre_num, rel, rel_num, local_part = m.group(1, 2, 3, 4, 8, 9, 11, 12, 13)
        if epoch:
            self.epoch = int(epoch[:-1])

        if rel:
            rel = rel.lower()

        if local_part:
            self.local_part = local_part[1:]

        components = (major + main_part).split(".")
        if len(components) > max_parts:
            return  # Invalid version

        self.given_components = tuple(map(int, components))
        while len(components) < max_parts:
            components.append(0)

        if rel in ("final", "post"):
            components.append(rel_num or 0)

        else:
            components.append(0)

        self.components = tuple(map(int, components))
        self.suffix = joined(rel, pre, delimiter="_", keep_empty=None) or None
        pre = "dev" if rel == "dev" else "_" + pre if pre else None  # Ensure 'dev' is sorted higher than other pre-release markers
        if pre:
            self.prerelease = (pre, int(pre_num or 0))

    @classmethod
    def from_text(cls, text, strict=False):
        """
        Args:
            text: Text (or any object, for convenience) to be parsed
            strict (bool): If False, use first substring from 'text' that looks like a version number

        Returns:
            (Version | None): Parsed version, if valid
        """
        if isinstance(text, Version):
            return text

        if text is not None:
            text = joined(text, delimiter=".")

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
        other = Version.from_text(other, strict=True)
        return isinstance(other, Version) and self.components == other.components and self.prerelease == other.prerelease

    def __lt__(self, other):
        other = Version.from_text(other, strict=True)
        if isinstance(other, Version):
            if self.components is None or other.components is None:
                return bool(other.components)

            if self.components == other.components:
                if self.prerelease is None or other.prerelease is None:
                    return bool(other.prerelease)

                return self.prerelease < other.prerelease

            return self.components < other.components

    def __le__(self, other):
        other = Version.from_text(other, strict=True)
        return isinstance(other, Version) and self < other or self == other

    def __ge__(self, other):
        other = Version.from_text(other, strict=True)
        return other is None or other <= self

    def __gt__(self, other):
        other = Version.from_text(other, strict=True)
        return other is None or other < self

    @property
    def is_final(self):
        """Is this a final version as per PEP-440?"""
        return self.is_valid and not self.local_part and not self.suffix

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

    @cached_property
    def mm(self):
        """(str): <major>.<minor>, often used in python paths, like config-3.9"""
        if self.is_valid:
            return joined(self.major, self.minor, delimiter=".")

    @property
    def patch(self):
        """(int): Patch part of version"""
        return self.components and self.components[2]


class PythonInstallation:
    """Models a specific python installation"""

    executable = None  # type: str # Full path to python executable
    is_invoker = False  # Is this the python we're currently running under?
    short_name = None  # type: str # Used to textually represent this installation
    problem = None  # type: str # String describing a problem with this installation, if there is one
    spec = None  # type: PythonSpec # Corresponding spec

    _equivalents = None  # type: set[str] # Paths that are equivalent to this python installation

    def __init__(self, exe, spec, equivalents=None, problem=None, short_name=None):
        """
        Args:
            exe (str): Path to executable
            spec (PythonSpec | None): Associated spec
            equivalents (list | set | None): Optional equivalent identifiers for this installation
            problem (str | None): Problem with this installation, if any
            short_name (str | None): Used to textually represent this installation
        """
        self.executable, self.short_name = _simplified_python_path(exe, short_name)
        self.folder = to_path(self.executable).parent if exe and not problem else None
        self.problem = problem
        self.spec = spec
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
        text = joined(self.problem or self.spec, self.is_invoker and "invoker", delimiter=", ")
        return "%s [%s]" % (short(self.short_name), text)

    def __str__(self):
        text = _R.colored(self.problem, "red") or self.spec
        text = joined(text, self.is_invoker and _R.colored("invoker", "green"), delimiter=", ")
        return "%s [%s]" % (_R.colored(short(self.short_name), "bold"), text)

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
    def major(self):
        """(int | None): Major python version, if any"""
        return self.spec and self.spec.version and self.spec.version.major

    @property
    def version(self):
        """(Version | None): Python version, if any"""
        return self.spec and self.spec.version

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
        self.version = Version(version)
        self.sys_prefix = sys_prefix
        self.base_prefix = base_prefix
        if not problem and not self.version.is_valid:
            problem = "invalid version '%s'" % self.version

        self.problem = problem


class _Introspect:
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


def _simplified_python_path(path, short_name):
    if path and ".framework/" in path:
        # Simplify macos ridiculous paths
        location = "/usr/bin"
        if "Cellar" in path:
            i = path.index("Cellar")
            location = path[:i].rstrip("/")
            if not location.endswith("bin"):
                location = os.path.join(location, "bin")

        m = re.search(r"Versions/([\d])", path)
        if m:
            path = os.path.join(location, "python%s" % m.group(1))

    if not short_name and path and "pyenv" in path:
        short_name = parent_folder(parent_folder(path))

    return path, short_name or path
