import json
import os
import re
from pathlib import Path
from typing import ClassVar

from runez.file import ls_dir
from runez.http import RestClient, urljoin
from runez.program import is_executable, run
from runez.system import _R, cached_property, flattened, joined, ltattr, resolved_path, short, UNSET

CPYTHON = "cpython"
RX_PYTHON_BASENAME = re.compile(r"^python(\d(\.\d+)?)?$")


class ArtifactInfo:
    """Info extracted from a typical python build artifact basename"""

    def __init__(
        self,
        basename,
        package_name,
        version,
        is_wheel=False,
        source=None,
        tags=None,
        wheel_build_number=None,
        last_modified=None,
        size=None,
    ):
        """
        Args:
            basename (str): Basename of artifact
            package_name (str): Package name, may not be completely standard
            version (Version): Package version
            is_wheel (bool): Is this artifact a wheel?
            source: Optional arbitrary object to track provenance of ArtifactInfo
            tags (str | None): Wheel tags, if any
            wheel_build_number (str | None): Wheel build number, if any
            last_modified (datetime.datetime | None): Timestamp when artifact was last modified, if available
            size (int | None): Size in bytes of artifact, if available
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
        self.last_modified = last_modified
        self.size = size

    @classmethod
    def from_basename(cls, basename, source=None, last_modified=None, size=None):
        """
        Args:
            basename (str): Basename to parse
            source: Optional arbitrary object to track provenance of ArtifactInfo
            last_modified (datetime.datetime | None): Timestamp when artifact was last modified, if available
            size (int | None): Size in bytes of artifact, if available

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
        return cls(
            basename,
            m.group(1),
            Version(m.group(2), canonical=None),
            is_wheel=is_wheel,
            source=source,
            tags=tags,
            wheel_build_number=wheel_build_number,
            last_modified=last_modified,
            size=size,
        )

    def __repr__(self):
        return self.relative_url or self.basename

    def __eq__(self, other):
        return isinstance(other, ArtifactInfo) and self.basename == other.basename

    def __lt__(self, other):
        """Ordered by source, then pypi_name, then version, then category"""
        return ltattr(self, other, "source", "pypi_name", "version", "category", t=ArtifactInfo)

    @property
    def category(self):
        return "wheel" if self.is_wheel else "sdist"

    @property
    def is_dirty(self):
        return self.version.is_dirty


class PypiStd:
    """
    Check/standardize pypi package names
    More strict than actual pypi (for example: names starting with a number are not considered value)
    """

    RX_ACCEPTABLE_PACKAGE_NAME = re.compile(r"^[a-z][\w.-]*[a-z\d]$", re.IGNORECASE)
    RR_PYPI = re.compile(r"([^a-z\d.-]+|--+)", re.IGNORECASE)
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
        """Standardized pypi package name, single dashes and alphanumeric chars allowed only"""
        if cls.is_acceptable(name):
            name = name.replace(".", "-")
            dashed = cls.RR_PYPI.sub("-", name).lower()
            return cls.RR_PYPI.sub("-", dashed)  # 2nd pass to ensure no `--` remains

    @classmethod
    def std_wheel_basename(cls, name):
        """Standardized wheel file base name, single underscores, dots and alphanumeric chars only"""
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

        url = index.format(name=pypi_name) if "{name}" in index else urljoin(index, f"{pypi_name}/")
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
            include_prerelease (bool): If True, include pre releases
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
            for _, infos in releases.items():
                for info in infos:
                    if not info.get("yanked"):
                        size = info.get("size")
                        upload_time = _R.lc.rm.to_datetime(info.get("upload_time"))
                        info = ArtifactInfo.from_basename(info.get("filename"), last_modified=upload_time, source=source, size=size)
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
    Internal canonical reference to a desired python installation, used to find python installations in `PythonDepot`
    Examples: cpython:3, cpython:3.9, pypy:3.9
    """

    def __init__(self, family, version, is_min_spec=False):
        """
        Args:
            family (str): Python family (cpython, conda, pypi, ...)
            version (Version | str): Desired version
            is_min_spec (bool): If True, match installations that are at least at `version`, e.g. cpython:3.10+
        """
        self.family = family
        self.version = Version.from_object(version)
        self.canonical = "%s:%s%s" % (family, version, "+" if is_min_spec else "")
        self.is_min_spec = is_min_spec

    def __repr__(self):
        return self.canonical

    def __hash__(self):
        return hash(self.canonical)

    def __eq__(self, other):
        return isinstance(other, PythonSpec) and self.canonical == other.canonical

    def __lt__(self, other):
        return ltattr(self, other, "family", "version", t=PythonSpec)

    def satisfies(self, other):
        """Does this spec satisfy 'other'?"""
        if isinstance(other, PythonSpec) and self.family == other.family:
            if other.is_min_spec:
                return self.version >= other.version

            return self.canonical.startswith(other.canonical)

    def represented(self, color=None, compact=CPYTHON):
        """
        Args:
            color (callable | None): Optional color to use
            compact (str | list | set | tuple | bool | None): Show version only, if `self.family` is mentioned in `compact`

        Returns:
            (str): Textual representation of this spec
        """
        text = self.canonical
        if compact and (compact is True or self.family in compact):
            text = self.version.text
            if self.is_min_spec:
                text += "+"

        return _R.colored(text, color)

    @classmethod
    def from_text(cls, text):
        """
        Args:
            text (str | None): Text to be converted into a PythonSpec() if possible, eg: 3.10, py310, python3.10, conda:3.10

        Returns:
            (PythonSpec | None): Parsed spec from given object, if valid
        """
        m = re.match(r"^(py|python|)(?P<version>\d+(\.\d+(.\w+)*)?)?(?P<min_spec>\+?)$", text)
        if m:
            version = Version.from_tox_like(m.group("version"), default="3")
            return cls(CPYTHON, version, is_min_spec=bool(m.group("min_spec"))) if version else None

        m = re.match(r"^(?P<family>cpython|conda|pypy):(?P<version>\d.*)$", text)
        if m:
            min_spec = False
            version = m.group("version")
            if version.endswith("+"):
                min_spec = True
                version = version[:-1]

            version = Version.from_tox_like(version)
            if version and version.is_valid:
                return cls(m.group("family"), version, is_min_spec=min_spec)

    @classmethod
    def from_object(cls, value):
        """
        Args:
            value: Value to transform into a PythonSpec, if possible

        Returns:
            (PythonSpec | None): Parsed spec from given object, if valid
        """
        if not value or isinstance(value, PythonSpec):
            return value or None

        if isinstance(value, Version):
            return cls(CPYTHON, value)

        if value:
            return cls.from_text(str(value))

    @classmethod
    def to_list(cls, values):
        """
        Args:
            values: Values to transform into a list of PythonSpec-s

        Returns:
            (list[PythonSpec]): Corresponding list of PythonSpec-s
        """
        values = flattened(values, split=",", transform=PythonSpec.from_object)
        values = [x for x in values if x and x.version]
        return values

    @classmethod
    def guess_family(cls, text):
        """
        Args:
            text (str | None): Text to examine

        Returns:
            (str): Guessed python family from given 'text' (typically path to installation)
        """
        if text:
            if "forge" in text or "conda" in text:
                return "conda"

            if "pypy" in text:
                return "pypy"

        return CPYTHON


class PythonDepot:
    """
    Find python installations on current machine

    Example usage:
        my_depot = PythonDepot("~/.pyenv/versions/**", "PATH")
        p = my_depot.find_python("3.7")
    """

    _preferred_python = None  # type: PythonInstallation  # Preferred python to use, if configured

    def __init__(self, *locations):
        """
        Args:
            locations (str | Path): Locations to scan
        """
        self.locations = [PythonInstallationLocation.from_location(x) for x in flattened(locations)]
        self.invoker = _R.lc.rm.SYS_INFO.invoker_python

    @cached_property
    def available_pythons(self):
        result = []
        for location in self.locations:
            result.extend(location.available_pythons)

        return result

    @property
    def preferred_python(self):
        """
        Returns:
            (PythonInstallation | None): Preferred python to use, either explicitly configured, or auto-determined from locations
        """
        if self._preferred_python is None:
            for location in self.locations:
                python = location.preferred_python
                if python:
                    self._preferred_python = python
                    break

        return self._preferred_python

    def set_preferred_python(self, *specs):
        """
        Args:
            specs (str | list[str]): List of preferred pythons, eg: 3.10, /usr/bin/python3, invoker
        """
        for spec in flattened(specs):
            python = self.find_python(spec)
            if python and not python.problem:
                self._preferred_python = python
                return

    def find_python(self, spec):
        """
        Args:
            spec (str | Path | PythonInstallation | PythonSpec | Version | None): Example: 3.7, py37, pypy:3.7, /usr/bin/python3

        Returns:
            (PythonInstallation): Object representing python installation (may not be usable, see reported .problem)
        """
        if not spec:
            return self.preferred_python or self.invoker

        if isinstance(spec, PythonInstallation):
            return spec

        if isinstance(spec, Path):
            return self._from_path(spec)

        python = self._find_python(spec)
        if python is None:
            if not isinstance(spec, Path):
                spec = Path(str(spec))

            python = PythonInstallation(spec)

        return python

    def _from_path(self, path: Path):
        for p in self.available_pythons:
            if p == path:
                return p

        return PythonInstallation.from_path(path, short_name=short(path))

    def _find_python(self, spec):
        if isinstance(spec, str):
            if spec.startswith(("~", ".", "/")) or "/" in spec or os.path.exists(spec):
                return self._from_path(Path(resolved_path(spec)))

            elif spec == "invoker":
                return self.invoker

            spec = PythonSpec.from_text(spec)

        else:
            spec = PythonSpec.from_object(spec)

        if not isinstance(spec, PythonSpec):
            return None

        preferred = self.preferred_python
        if preferred and preferred.satisfies(spec):
            return preferred

        for location in self.locations:
            python = location.find_python(spec)
            if python is not None:
                return python

        if self.invoker and self.invoker.satisfies(spec):
            return self.invoker

    def representation(self):
        """(str): Textual representation of available pythons"""
        result = []
        for location in self.locations:
            result.append(location.representation())

        return joined(result, delimiter="\n\n") or "No PythonDepot locations configured"


class Version:
    """
    Parse versions according to PEP-440, including ordering.
    """

    text: str

    def __init__(self, text, max_parts=5, canonical=False):
        """
        Args:
            text (str | None): Text to be parsed
            max_parts (int): Maximum number of parts (components) to consider version valid
            canonical (bool | None): None: loose parsing, False: strict parsing, version left as-is, True: Turn into canonical PEP-440
        """
        self.given_text = text
        self.given_components = None  # Components as given by 'text'
        self.text = text or ""
        self.components = None  # tuple of components with exactly 'max_parts', autofilled with zeros
        self.epoch = 0
        self.local_part = None
        self.prerelease = None
        self.suffix = None
        m = _R.lc.rx_version.match(self.text)
        if not m:
            self.ignored = self.text
            return

        self.ignored = m.group("ignored") or None
        # 'canonical' set to None allows to continue even if there were extraneous bits
        if canonical is not None and self.ignored:
            return

        self.text = m.group("vtext")
        self.epoch = int(m.group("epoch") or 0)
        self.local_part = m.group("local") or None
        pre, pre_num, rel, rel_num, dev, dev_num = m.group("pre", "pre_num", "rel", "rel_num", "dev", "dev_num")
        if pre == "c":
            pre = "rc"

        # Order: .devN, aN, bN, rcN, <no suffix>, .postN
        self.suffix = joined(pre, rel, dev, delimiter=".", keep_empty=None) or None
        if pre or dev:
            self.prerelease = pre or "", int(pre_num or 0), rel or "", int(rel_num or 0), dev or "z", int(dev_num or 0)
            if pre:
                rel = rel_num = None  # rc.post does not count as .post (but a .post.dev does)

        components = [int(c) for c in m.group("main").split(".")]
        if len(components) > max_parts:
            return  # Invalid version, too many parts

        self.given_components = tuple(components)
        while len(components) < max_parts:
            components.append(0)

        self.release_number = None if rel_num is None else int(rel_num or 0)
        components.append(int(rel_num or 0))
        components.append(rel or "")
        self.components = tuple(components)
        if canonical is True:
            self.text = self.pep_440

    @classmethod
    def extracted_from_text(cls, text):
        """
        Args:
            text (str): Text to extract version from

        Returns:
            (Version | None): Parsed version, if a valid one was found
        """
        m = _R.lc.rx_version.search(text)
        if m:
            v = cls(m.group("vtext"), canonical=None)
            if v.is_valid:
                return v

    @classmethod
    def from_object(cls, obj):
        """
        Args:
            obj: Object to turn into a Version, if possible

        Returns:
            (Version | None): Corresponding version object, if valid
        """
        if obj:
            if isinstance(obj, Version):
                return obj if obj.is_valid else None

            if not isinstance(obj, str):
                obj = joined(obj, delimiter=".")

            v = cls(obj)
            if v.is_valid:
                return v

    @classmethod
    def from_tox_like(cls, text, default=None):
        """Parse a version taking into account tox-like versions like '310' meaning '3.10'"""
        if text and re.match(r"^(\d\d+)$", text):
            return cls.from_object((text[0], text[1:]))

        return cls.from_object(text or default)

    def __repr__(self):
        return self.text

    def __hash__(self):
        return hash(self.text)

    def __eq__(self, other):
        if not self.is_valid:
            return isinstance(other, Version) and self.text == other.text

        other = Version.from_object(other)
        return (
            isinstance(other, Version)
            and self.epoch == other.epoch
            and self.components == other.components
            and self.prerelease == other.prerelease
            and self.local_part == other.local_part
        )

    def __lt__(self, other):
        other = Version.from_object(other)
        if isinstance(other, Version):
            if self.epoch != other.epoch:
                return self.epoch < other.epoch

            if self.components is None or other.components is None:
                return bool(other.components)

            if self.components == other.components:
                if self.prerelease == other.prerelease:
                    my_parts = self.local_parts
                    other_parts = other.local_parts
                    if my_parts is None or other_parts is None:
                        return bool(other_parts)

                    for mine, theirs in zip(my_parts, other_parts):
                        if mine == theirs:
                            continue

                        if theirs.isdigit():
                            return not mine.isdigit() or int(mine) < int(theirs)

                        if mine.isdigit():
                            return False

                        return mine < theirs

                    return len(my_parts) < len(other_parts)

                if self.prerelease is None or other.prerelease is None:
                    return bool(self.prerelease)

                return self.prerelease < other.prerelease

            return self.components < other.components

    def __le__(self, other):
        other = Version.from_object(other)
        return isinstance(other, Version) and self < other or self == other

    def __ge__(self, other):
        other = Version.from_object(other)
        return other is None or other <= self

    def __gt__(self, other):
        other = Version.from_object(other)
        return other is None or other < self

    @cached_property
    def given_components_count(self):
        return len(self.given_components) if self.given_components else 0

    @cached_property
    def local_parts(self):
        """Local parts are only needed when comparing versions that differ solely by local part..."""
        if self.local_part:
            v = getattr(self, "_local_parts", None)
            if v is None:
                v = self.local_part.split(".")
                self._local_parts = v

            return v

    @cached_property
    def is_dirty(self):
        """Is this version marked as 'dirty'?"""
        return self.local_part and "dirty" in self.local_part

    @cached_property
    def is_final(self):
        """Is this a final version as per PEP-440?"""
        return self.is_valid and not self.prerelease

    @cached_property
    def is_valid(self):
        """Is this version valid?"""
        return self.components is not None

    @cached_property
    def main(self):
        """(str): Main part of version (Major.minor.patch)"""
        if self.given_components:
            return ".".join(str(x) for x in self.given_components[:3])

    @cached_property
    def major(self):
        """(int): Major part of version"""
        if self.given_components_count >= 1:
            return self.components and self.components[0]

    @cached_property
    def minor(self):
        """(int): Minor part of version"""
        if self.given_components_count >= 2:
            return self.components and self.components[1]

    @cached_property
    def mm(self):
        """(str): <major>.<minor>, often used in python paths, like config-3.9"""
        if self.minor is not None:
            return "%s.%s" % (self.major, self.minor)

    @property
    def patch(self):
        """(int): Patch part of version"""
        if self.given_components_count >= 3:
            return self.components and self.components[2]

    @cached_property
    def pep_440(self):
        """PEP-440 canonical version"""
        if self.is_valid:
            result = []
            if self.epoch:
                result.append(f"{self.epoch}!")

            result.append(self.main)
            if self.prerelease:
                if self.prerelease[0]:
                    result.append("%s%s" % (self.prerelease[0], self.prerelease[1]))

                if self.prerelease[2]:
                    result.append(".%s%s" % (self.prerelease[2], self.prerelease[3]))

                if self.prerelease[4] and self.prerelease[4] != "z":
                    result.append(".%s%s" % (self.prerelease[4], self.prerelease[5]))

            if self.release_number is not None:
                result.append(".post%s" % self.release_number)

            if self.local_part:
                result.append(f"+{self.local_part}")

            return "".join(result)


class PythonInstallation:
    """Models a specific python installation"""

    def __init__(self, executable, short_name=None):
        """
        Args:
            executable (Path): Path to python executable
            short_name (str | None): Short name to textually represent this installation
        """
        self.executable = executable
        self.short_name = short_name or short(executable)
        self.real_exe, inspection = PythonSimpleInspection.exe_inspection(executable)
        self.inspection = inspection
        self.problem = inspection.problem
        version = None
        if not self.problem:
            version = Version(inspection.version)
            if not version.is_valid:
                self.problem = f"invalid version '{version.text}'"
                version = None

        self.full_version = version

    def __repr__(self):
        return self.representation(is_coloring=False)

    def __str__(self):
        return self.representation()

    def __eq__(self, other):
        if isinstance(other, Path):
            return other == self.executable or other == self.real_exe

        return isinstance(other, PythonInstallation) and self.real_exe == other.real_exe

    def __lt__(self, other):
        if isinstance(other, PythonInstallation):
            if self.full_spec is None or other.full_spec is None:
                return other.full_spec is not None or str(self.executable) < str(other.executable)

            if self.full_spec == other.full_spec:
                return str(self.executable) < str(other.executable)

            return self.full_spec < other.full_spec

    def representation(self, is_coloring=UNSET, preferred=None):
        """
        Args:
            is_coloring (bool): Whether text should be colored (default: yes on tty)
            preferred (PythonInstallation | None): Highlight preferred python (if this installation is the preferred one)

        Returns:
            (str): Short textual representation of this installation
        """
        more_info = []
        if self.problem:
            more_info.append(_R.colored(self.problem, "red", is_coloring=is_coloring))

        full_spec = self.full_spec
        if full_spec and full_spec.version.text not in self.short_name:
            more_info.append(full_spec.represented())

        if preferred and self.executable == preferred.executable:
            more_info.append(_R.colored("preferred", "dim", is_coloring=is_coloring))

        if self.machine and self.machine != _R.lc.rm.SYS_INFO.platform_id.arch:
            more_info.append(_R.colored(self.machine, "dim", is_coloring=is_coloring))

        text = _R.colored(self.short_name, "bold", is_coloring=is_coloring)
        if more_info:
            return "%s [%s]" % (text, ", ".join(more_info))

        return text

    @classmethod
    def from_path(cls, path, short_name=None):
        """
        Args:
            path (Path): Path to folder or file
            short_name (str | None): Short name to use for textual representation of this installation

        Returns:
            (PythonInstallation): Associated installation
        """
        if path.is_dir():
            return cls.from_folder(path, short_name=short_name)

        return cls(path, short_name=short_name)

    @classmethod
    def from_folder(cls, folder, short_name=None):
        """
        Args:
            folder (Path): Path to folder
            short_name (str | None): Short name to use for textual representation of this installation

        Returns:
            (PythonInstallation): Associated installation
        """
        if folder.name != "bin":
            bin_folder = folder / "bin"
            if bin_folder.is_dir():
                folder = bin_folder

        path = folder / "python3"
        if not is_executable(path):
            path = folder / "python"

        return cls(path, short_name=short_name)

    @property
    def is_invoker(self):
        """Is this the python installation current execution is using?"""
        return self == _R.lc.rm.SYS_INFO.invoker_python

    @cached_property
    def family(self):
        return PythonSpec.guess_family(str(self.real_exe))

    @cached_property
    def full_spec(self):
        """Full spec, , e.g: cpython:3.11.6"""
        if self.full_version:
            return PythonSpec(self.family, self.full_version)

    @cached_property
    def mm(self):
        """Major/minor version, e.g: cpython:3.11"""
        if self.full_version:
            return Version(self.full_version.mm)

    @cached_property
    def mm_spec(self):
        """Major/minor spec, e.g: cpython:3.11"""
        if self.mm:
            return PythonSpec(self.family, self.mm)

    @cached_property
    def machine(self):
        return self.inspection.machine

    def satisfies(self, given_spec):
        """
        Args:
            given_spec (PythonSpec): Spec expressed by user or configuration

        Returns:
            (bool): True if this python installation satisfies it
        """
        if given_spec and self.family == given_spec.family and not self.problem:
            spec = self.full_spec if given_spec.version.given_components_count > 2 else self.mm_spec
            return spec.satisfies(given_spec)


class PythonInstallationLocation:
    """
    Local source where python installations can be found

    Locations can be specified as:
    - <some-folder>: look for <some-folder>/pythonM.m exes
    - <some-folder>/python*: look for <some-folder>/pythonM.m/bin/pythonM.m (eg: /apps/python*)
    - <some-folder>/**: look for <some-folder>/**/bin/pythonM.m (eg: ~/.pyenv/versions/**)
    - PATH: Scan PATH env var for python exes
    """

    def __init__(self, location):
        self.location = location
        self._preferred_python = UNSET  # type: PythonInstallation # Auto-selected preferred python from this location

    def __repr__(self):
        return short(self.location)

    @classmethod
    def from_location(cls, location):
        if isinstance(location, str):
            if location == "PATH":
                return PythonInstallationLocationPathEnvVar(location)

            if location.endswith("/**"):
                return PythonInstallationLocationPyenv(location)

            if location.endswith("/python*"):
                return PythonInstallationLocationSubFolders(location)

        return PythonInstallationLocation(location)

    def _auto_determined_preferred(self):
        """By default, look for a `python3` symlink and consider it to be the preferred python"""
        for basename in ("python3", "python"):
            path = Path(self.location) / basename
            if path.is_symlink():
                symlink = os.readlink(path)
                m = RX_PYTHON_BASENAME.match(symlink)
                if m and m.group(2):
                    # We have a python -> pythonM.m symlink
                    python = PythonInstallation(path.parent / symlink)
                    if not python.problem:
                        return python

    def _scanned_location(self):
        """
        Returns:
            (list[PythonInstallation]): Python installations found in this location
        """
        # Default: pythons from a folder containing pythonM.m symlinks, eg: /opt/my-python-binaries/
        result = []
        for item in ls_dir(self.location):
            if item.is_file():
                m = RX_PYTHON_BASENAME.match(item.name)
                if m and m.group(2):
                    python = PythonInstallation(item)
                    if not python.problem:
                        result.append(python)

        return sorted(result, reverse=True)

    @property
    def preferred_python(self):
        """(PythonInstallation | None): Preferred python found in this location"""
        if self._preferred_python is UNSET:
            self._preferred_python = self._auto_determined_preferred()

        return self._preferred_python

    @cached_property
    def available_pythons(self):
        """
        Returns:
            (list[PythonInstallation]): Python installations found in this location
        """
        return self._scanned_location()

    def find_python(self, spec):
        for python in self.available_pythons:
            if python.satisfies(spec):
                return python

    def representation(self):
        """(str): Textual representation of available pythons"""
        if not self.available_pythons:
            return "No python installations found in '%s'" % _R.colored(self, "orange")

        text = _R.lc.rm.plural(self.available_pythons, "python installation")
        text = f"{text} in {self}:\n"
        text += "\n".join(p.representation(preferred=self.preferred_python) for p in self.available_pythons)
        return text


class PythonInstallationLocationPathEnvVar(PythonInstallationLocation):
    """Pythons from PATH env var"""

    def _auto_determined_preferred(self):
        """When using PATH env var, don't pick any preferred python"""

    def _scanned_location(self):
        result = []
        venv = os.environ.get("VIRTUAL_ENV")
        for folder in flattened(os.environ.get("PATH"), split=os.pathsep):
            if venv and folder.startswith(venv):
                continue  # Ignore python installations from virtualenv

            general = []  # General symlinks, eg: `python3` and `python`
            major_minors = []  # Major.minor symlinks, eg: `python3.7`
            for item in ls_dir(folder):
                if is_executable(item):
                    m = RX_PYTHON_BASENAME.match(item.name)
                    if m:
                        python = PythonInstallation(item)
                        if not python.problem:
                            target = major_minors if m.group(2) else general
                            target.append(python)

            result.extend(sorted(general, key=lambda x: x.executable))
            result.extend(sorted(major_minors, reverse=True))

        return result


class PythonInstallationLocationPyenv(PythonInstallationLocation):
    """Pythons from pyenv-like location, eg: ~/.pyenv/versions/**"""

    def _scanned_location(self):
        result = []
        for item in ls_dir(os.path.dirname(self.location)):
            if not item.is_symlink() and item.is_dir():
                bin_folder = item / "bin"
                if bin_folder.is_dir():
                    python = PythonInstallation.from_folder(bin_folder, short_name=short(item))
                    if not python.problem:
                        result.append(python)

        return sorted(result, reverse=True)


class PythonInstallationLocationSubFolders(PythonInstallationLocation):
    """Pythons from python* directories, eg: /apps/python*"""

    def _scanned_location(self):
        result = []
        for item in ls_dir(os.path.dirname(self.location)):
            if item.is_dir():
                m = RX_PYTHON_BASENAME.match(item.name)
                if m and m.group(2):
                    python = PythonInstallation(item / "bin" / item.name, short_name=short(item))
                    if not python.problem:
                        result.append(python)

        return sorted(result, reverse=True)


class PythonSimpleInspection:
    """Simple inspection (version and arch) of a python executable, cached to avoid expensive python process invocations"""

    _cached: ClassVar = {}

    def __init__(self, version=None, machine=None, problem=None):
        self.version = version
        self.machine = machine
        self.problem = problem

    def __repr__(self):
        return self.problem or f"{self.version} ({self.machine})"

    @classmethod
    def register(cls, key, real_exe, inspection):
        cls._cached[key] = (real_exe, inspection)
        cls._cached[real_exe] = (real_exe, inspection)

    @classmethod
    def exe_inspection(cls, executable):
        cached = cls._cached.get(executable)
        if cached is not None:
            return cached

        real_exe = executable.resolve()
        cached = cls._cached.get(real_exe)
        if cached is not None:
            return cached

        if not is_executable(executable):
            return real_exe, cls(problem="not available")

        try:
            import runez._inspect

            r = run(real_exe, runez._inspect.__file__, dryrun=False, fatal=False, logger=None)
            if r.succeeded:
                result = json.loads(r.output)
                if not isinstance(result, dict) or not result.get("version"):
                    return real_exe, cls(problem=f"internal error: _inspect.py returned '{short(result)}'")

                result = cls(**result)

            else:
                result = cls(problem=short(r.full_output))

        except Exception as e:
            result = cls(problem=f"internal error: {e}")

        cls.register(executable, real_exe, result)
        return real_exe, result
