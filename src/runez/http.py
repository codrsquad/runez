"""
Simple REST client with --dryrun support, and optionally 'fatal=...', 'logger=...' (same as all other IO related runez functions).

Benefits and use case:
- Convenient for short-run CLIs, who typically don't do anything sophisticated (with threads etc) when accessing REST services
- Simplified code (no need to repeat session = requests.Session() ... etc)
- Convenience touches like 'base_url'
- Can support different implementations (anything that has a requests-like API will do: session.get(), .post() etc)
- Simple mocks for tests

Usage pattern:
    from runez.http import RestClient

    # You can either have a global 'new_session'
    def my_session_creator(client: RestClient, foo=None, ...):
        return requests.Session()  # customized 'session'

    RestClient.new_session = my_session_creator
    MY_SERVER = RestClient("https://example.net", foo="my-foo")

    # Or do it per client:
    def my_dedicated_creator(foo=None, ...):
        return requests.Session()  # customized 'session'

    MY_SERVER = RestClient("https://example.net", spec="my-spec", new_session=my_dedicated_creator)

    # Then use the client
    response = MY_SERVER.get("api/v1/....", fatal=False, dryrun=False)
"""

import functools
import json
import os
import urllib.parse
from pathlib import Path

from runez.file import TempFolder, to_path, untar, write
from runez.system import _R, abort, joined, short, stringified, SYS_INFO, UNSET


def urljoin(base, url):
    """Join base + url, considering that `base` is intended to be the base url of a REST end point"""
    if not base:
        return url

    if not url:
        return base

    if not base.endswith("/"):
        # Annoying edge case: urljoin() removes the last component of url if it's not `/` terminated, which can be surprising
        base += "/"

    return urllib.parse.urljoin(base, url, allow_fragments=False)


class RestClient:
    """REST client with good defaults for retry, timeout, ... + support for --dryrun mode etc"""

    _sessions = {}  # Cached underlying 'new_session()' objects, mostly so tests can intercept this to mock out accesses

    def __init__(self, base_url=None, headers=None, timeout=30, user_agent=SYS_INFO.user_agent, new_session=None, **session_spec):
        """
        Args:
            base_url (str | None): Base url of remote REST server
            headers (dict | None): Default headers to use
            timeout (int): Default timeout in seconds
            user_agent (str | None): User-Agent to use for outgoing calls coming from this client
            new_session (callable): Optionally client-dedicated 'new_session()` creator
        """
        self.session_spec = session_spec
        self.key = tuple(session_spec.items())
        self.base_url = base_url
        self.headers = {}
        self.timeout = timeout
        self.user_agent = user_agent
        if user_agent:
            self.headers["User-Agent"] = user_agent

        if headers:
            self.headers.update(headers)

        if new_session is not None:
            self.new_session = new_session

    @classmethod
    def new_session(cls, **session_spec):
        """
        Args:
            **session_spec: Spec that underlying implementation can use to tweak returned session object

        Returns:
            Session object, needs to have a requests-like .get(), .put() etc
        """
        return RestClient.new_requests_session(
            http_adapter=session_spec.pop("http_adapter", None),
            https_adapter=session_spec.pop("https_adapter", None),
            retry=session_spec.pop("retry", None),
        )

    @staticmethod
    def default_retry():
        from urllib3 import Retry

        return Retry(backoff_factor=1, status_forcelist={413, 429, 500, 502, 503, 504})

    @staticmethod
    def new_requests_session(http_adapter=None, https_adapter=None, retry=None):
        """Implementation using requests.Session(), you must provide a custom new_session() if you don't have `requests` as a req"""
        import requests
        from requests.adapters import HTTPAdapter

        session = requests.Session()
        if retry is None:
            retry = RestClient.default_retry()

        if retry and https_adapter is None:
            https_adapter = HTTPAdapter(max_retries=retry)

        if retry and http_adapter is None:
            http_adapter = HTTPAdapter(max_retries=retry)

        if https_adapter:
            session.mount("https://", https_adapter)

        if http_adapter:
            session.mount("http://", http_adapter)

        return session

    def full_url(self, url):
        """
        Args:
            url (str): Relative URL

        Returns:
            (str): Absolute URL, auto-completed with `self.base_url`
        """
        return urljoin(self.base_url, url)

    def download(self, url, destination, fatal=True, logger=UNSET, dryrun=UNSET, **kwargs):
        """
        Args:
            url (str): URL of resource to download (may be absolute, or relative to self.base_url)
            destination (str | Path): Path to local file where to store the download
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            **kwargs: Passed-through to underlying session.get() call

        Returns:
            Response from underlying REST GET call
        """
        response = self._get_response("GET", url, kwargs, dryrun, fatal, logger, action="download")
        if response.ok:
            write(destination, response.content, fatal=fatal, logger=logger, dryrun=dryrun)

        return response

    def untar(self, url, destination, fatal=True, logger=UNSET, dryrun=UNSET, **kwargs):
        """
        Args:
            url (str): URL of .tar.gz to unpack (may be absolute, or relative to self.base_url)
            destination (str | Path): Path to local folder where to untar url
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            **kwargs: Passed-through to underlying session.get() call

        Returns:
            Response from underlying REST GET call
        """
        destination = to_path(destination).absolute()
        with TempFolder():
            tarball_path = to_path(os.path.basename(url)).absolute()
            response = self.download(url, tarball_path, fatal=fatal, logger=logger, dryrun=dryrun, **kwargs)
            if response.ok:
                untar(tarball_path, destination, fatal=fatal, logger=logger, dryrun=dryrun)

            return response

    def get_response(self, url, fatal=True, logger=UNSET, **kwargs):
        """
        Args:
            url (str): Remote URL (may be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            **kwargs: Passed-through to underlying session.get() call

        Returns:
            Response from underlying REST GET call
        """
        return self._get_response("GET", url, kwargs, False, fatal, logger)

    def delete(self, url, fatal=True, logger=UNSET, dryrun=UNSET, **kwargs):
        """Same as underlying .delete(), but respecting 'dryrun' mode

        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            **kwargs: Passed-through to underlying requests .delete() call

        Returns:
            (requests.Response): Underlying 'response', unless we had to .abort()
        """
        return self._get_response("DELETE", url, kwargs, dryrun, fatal, logger)

    def get(self, url, fatal=True, logger=UNSET, **kwargs):
        """
        Args:
            url (str): Remote URL (may be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            **kwargs: Passed-through to underlying session.get() call

        Returns:
            (dict | None): Deserialized .json() from response, if available
        """
        response = self.get_response(url, fatal=fatal, logger=logger, **kwargs)
        if response.ok:
            return response.json()

    def head(self, url, fatal=True, logger=UNSET, **kwargs):
        """
        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            **kwargs: Passed-through to underlying session.head() call

        Returns:
            Response from underlying REST HEAD call
        """
        return self._get_response("HEAD", url, kwargs, False, fatal, logger)

    def post(self, url, fatal=True, logger=UNSET, dryrun=UNSET, **kwargs):
        """Same as underlying .post(), but respecting 'dryrun' mode

        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            **kwargs: Passed-through to underlying requests .post() call

        Returns:
            (requests.Response): Underlying 'response', unless we had to .abort()
        """
        return self._get_response("POST", url, kwargs, dryrun, fatal, logger)

    def put(self, url, fatal=True, logger=UNSET, dryrun=UNSET, **kwargs):
        """
        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            **kwargs: Passed-through to underlying requests .put() call

        Returns:
            (requests.Response): Underlying 'response', unless we had to .abort()
        """
        return self._get_response("PUT", url, kwargs, dryrun, fatal, logger)

    def url_exists(self, url, logger=False):
        """
        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter

        Returns:
            (bool): True if remote URL exists (ie: not a 404)
        """
        response = self.head(url, fatal=False, logger=logger)
        return bool(response and response.ok)

    def _get_response(self, method, url, kwargs, dryrun, fatal, logger, action=None):
        """
        Args:
            method (str): Underlying method to call
            url (str): Remote URL (may be absolute, or relative to self.base_url)
            kwargs: Keyword arguments, auto-completed and passed-through to underlying requests.Session()-like call
            dryrun (bool): Optionally override current dryrun setting
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | None): Logger to use, False to log errors only, None to disable log chatter
            action (str | None): Action to refer to in dryrun message (default: method)

        Returns:
            Response from underlying requests.Session()-like call
        """
        absolute_url = self.full_url(url)
        session = self._sessions.get(self.key)
        if session is None:
            session = self._sessions[self.key] = self.new_session(**self.session_spec)

        message = "%s %s" % (action or method, absolute_url)
        if _R.hdry(dryrun, logger, message):
            return MockResponse(method, absolute_url, dict(message="dryrun %s" % message), 200, kwargs)

        kwargs.setdefault("timeout", self.timeout)
        headers = self.headers
        gh = kwargs.get("headers")
        if gh:
            headers = dict(headers) if headers else {}
            headers.update(gh)

        if headers:
            kwargs["headers"] = headers

        fhandles = []
        data = kwargs.get("data")
        if isinstance(data, Path):
            kwargs["data"] = open(data, mode="rb")
            fhandles.append(kwargs["data"])

        filepaths = kwargs.pop("filepaths", None)
        if filepaths:
            files = {}  # Convenience / simplified multipart upload
            for k, fpath in filepaths.items():
                fh = open(fpath, mode="rb")
                fhandles.append(fh)
                files[k] = (fpath.name, fh)

            kwargs["files"] = files

        try:
            func = getattr(session, method.lower())
            response = func(absolute_url, **kwargs)

        finally:
            for f in fhandles:
                f.close()

        if fatal or logger is not None:
            msg = self.response_description(response)
            if fatal and not response.ok:
                abort(msg)

            _R.hlog(logger, msg)

        return response

    @staticmethod
    def extract_message(data):
        """
        Try to get to the point of a returned REST json bit, extract meaningful message if possible.
        Otherwise, we fallback the .text of response (which may be verbose / hard to read)
        """
        if not data:
            return None

        if data and isinstance(data, str):
            return data.strip()

        if isinstance(data, dict):
            msg = RestClient.extract_message(data.get("message"))
            if msg:
                return msg

            msg = RestClient.extract_message(data.get("error"))
            if msg:
                return msg

            return RestClient.extract_message(data.get("errors"))

        if isinstance(data, list):
            for item in data:
                msg = RestClient.extract_message(item)
                if msg:
                    return msg

    @staticmethod
    def response_snippet(response, size=1024):
        """Meaningful text from 'response'"""
        if response.ok or response.status_code == 404:
            return ""

        try:
            msg = RestClient.extract_message(response.json())

        except Exception:
            msg = None

        if msg is None or len(msg) < 6:
            msg = "%s %s" % (msg or "", stringified(response.text).strip() or "-empty response text-")
            msg = msg.strip()

        if len(msg) > size:
            msg = "%s..." % msg[:size]

        return msg

    @staticmethod
    def response_description(response, history=True):
        """Description showing what happened with requests 'response', fir .debug() output, or .error() reporting"""
        if response is None:
            return ""

        method = response.request and response.request.method
        status = joined(response.status_code, response.reason, keep_empty=None)
        msg = "%s %s [%s] %s" % (method, response.url, status, RestClient.response_snippet(response))
        msg = msg.strip()
        if history and response.history:
            h = (RestClient.response_description(r, history=False) for r in response.history)
            msg = joined(msg, "\n-- Response history: --", h, delimiter="\n", keep_empty=None)

        return msg


class GlobalHttpCalls:
    """Allows to forbid/allow outgoing http(s) call during test runs"""

    _original_urlopen = None

    def __init__(self, allowed):
        """We're used as a context manager"""
        self.allowed = allowed
        self.was_allowed = None

    def __repr__(self):
        return "allowed" if self.allowed else "forbidden"

    def __enter__(self):
        self.was_allowed = self.allow(self.allowed)
        return self

    def __exit__(self, *_):
        self.allow(self.was_allowed)

    @staticmethod
    def intentionally_disabled(*_, **__):
        """Used as replacement of urlopen(), when external http calls are forbidden"""
        assert False, "Outgoing requests are intentionally forbidden in tests"

    @classmethod
    def is_forbidden(cls):
        """Are outgoing http calls currently allowed?"""
        return cls._original_urlopen is not None

    @classmethod
    def allow(cls, allowed=True):
        """Allow outgoing http(s) calls"""
        from urllib3.connectionpool import HTTPConnectionPool

        was_allowed = cls._original_urlopen is None
        if allowed:
            if cls._original_urlopen is not None:
                HTTPConnectionPool.urlopen = cls._original_urlopen
                cls._original_urlopen = None

        elif cls._original_urlopen is None:
            cls._original_urlopen = HTTPConnectionPool.urlopen
            HTTPConnectionPool.urlopen = GlobalHttpCalls.intentionally_disabled

        return was_allowed

    @classmethod
    def forbid(cls):
        """Forbid outgoing http(s) calls"""
        return cls.allow(False)


def mock_http(*specs, base=None, default_status=404):
    """
    Usage example:

    SOME_SESSION = RestAPI("https://example.com")

    @mock_http({
        "_base": "https://example.com"
        "foo": {"some": "payload"}
    })
    def test_foo():
        assert SOME_SESSION.get("foo") == {"some": "payload"}

    Args:
        *specs (dict): Map of url -> what to return
        base (str): Base url
        default_status (int): Default status code to use for all queries that don't have a url declared in 'specs' (default: 404)

    Returns:
        Function decorator that will enact the mock
    """
    return MockHttp(*specs, base=base, default_status=default_status)


class MockHttp:
    """Intercept and mock out outgoing RestClient calls"""

    def __init__(self, *specs, base=None, default_status=404):
        self.specs = {}
        self.default_status = default_status
        self._original_new_session = None
        for by_endpoint in specs:
            assert isinstance(by_endpoint, dict), "Mocked response specs must be a dict of url -> what to return"
            base_url = by_endpoint.pop("_base", base)  # Convenience: allow to "factor out" the base url
            for url, rspec in by_endpoint.items():
                url = urljoin(base_url, url)
                if not isinstance(rspec, MockResponseSpec):
                    rspec = MockResponseSpec(url, rspec)

                self.specs[url] = rspec

    def __repr__(self):
        return "%s specs" % len(self.specs)

    def __call__(self, func):
        """We're used as a decorator"""
        @functools.wraps(func)
        def inner(*args, **kwargs):
            self.__enter__()
            try:
                return func(*args, **kwargs)

            finally:
                self.__exit__()

        return inner

    def __enter__(self):
        """We're used as a context manager"""
        self._original_new_session = RestClient.new_session
        RestClient.new_session = self._new_session
        RestClient._sessions = {}
        return self

    def __exit__(self, *_):
        RestClient.new_session = self._original_new_session
        RestClient._sessions = {}

    def _new_session(self, **session_spec):
        return self

    def _get_response(self, method, url, kwargs):
        spec = self.specs.get(url)
        if spec is None:
            spec = MockResponseSpec(url, (self.default_status, dict(message="Default status code %s" % self.default_status)))

        return spec.get_response(method, kwargs)

    def delete(self, url, **kwargs):
        """Mocked out GET call"""
        return self._get_response("DELETE", url, kwargs)

    def get(self, url, **kwargs):
        """Mocked out GET call"""
        return self._get_response("GET", url, kwargs)

    def head(self, url, **kwargs):
        """Mocked out HEAD call"""
        return self._get_response("HEAD", url, kwargs)

    def post(self, url, **kwargs):
        """Mocked out POST call"""
        return self._get_response("POST", url, kwargs)

    def put(self, url, **kwargs):
        """Mocked out PUT call"""
        return self._get_response("PUT", url, kwargs)


class MockedRequest:
    """Pretends to be a requests' Request"""

    def __init__(self, method, url):
        self.method = method
        self.url = url


class MockResponse:
    """Pretends to be a requests' Response"""

    def __init__(self, method, url, payload, status_code, kwargs):
        self.url = url
        self.status_code = status_code
        self.kwargs = kwargs
        self.history = tuple()
        self.request = MockedRequest(method, url)
        if payload is None or isinstance(payload, str):
            self.payload = payload

        else:
            self.payload = json.dumps(payload)

    def __repr__(self):
        return "%s %s" % (self.status_code, short(self.payload))

    @property
    def content(self):
        return self.text.encode("UTF-8")

    def json(self):
        return json.loads(self.text)

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            from requests import HTTPError

            raise HTTPError(self.reason, response=self)

    @property
    def reason(self):
        if self.ok:
            return ""

        if 400 <= self.status_code < 500:
            return "Bad request"

        return "Internal error"

    @property
    def text(self):
        return stringified(self.payload)


class MockResponseSpec:
    """Represents a user-given spec of how to mock a given url"""

    def __init__(self, url, spec):
        self.url = url
        self.spec = spec

    def get_response(self, method, kwargs):
        """
        Args:
            method (str): Method 'self.url' was accessed with
            kwargs: Keyword arguments passed-through to underlying requests call

        Returns:
            (MockResponse): Mocked response
        """
        if isinstance(self.spec, BaseException):
            raise self.spec

        if isinstance(self.spec, type) and issubclass(self.spec, BaseException):
            raise self.spec("Simulated crash")

        result = self.spec(method, self.url, **kwargs) if callable(self.spec) else self.spec
        if isinstance(result, MockResponse):
            return result

        if isinstance(result, int):
            status_code, payload = result, "status %s" % result

        elif isinstance(result, (dict, list, str)):
            status_code, payload = 200, result

        elif isinstance(result, tuple) and len(result) == 2:
            status_code, payload = result

        else:
            # Spec does not return a "known result form": int, or <content>, or tuple(int, <content>)
            assert False, "Check mock response: %s" % result

        return MockResponse(method, self.url, payload, status_code, kwargs)

    def __repr__(self):
        return "%s %s" % (self.url, self.spec)
