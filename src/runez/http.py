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

    # You can replace the default RestClient.handler
    RestClient.handler = MyHandler
    MY_CLIENT = runez.http.RestClient("https://example.net", foo="my-foo")

    # Or do it per client:
    MY_CLIENT = runez.http.RestClient("https://example.net", spec="my-spec", handler=MyHandler)

    # Then use the client
    response = MY_CLIENT.get("api/v1/....", fatal=False, dryrun=False)
"""

import functools
import json
import os
import urllib.parse
from pathlib import Path

from runez.file import TempFolder, to_path, untar
from runez.system import _R, abort, find_caller_frame, stringified, SYS_INFO, UNSET


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
    def allowed(cls, func):
        """Decorator for test_ functions, temporarily allows external requests"""
        @functools.wraps(func)
        def inner(*args, **kwargs):
            with GlobalHttpCalls(True):
                return func(*args, **kwargs)

        return inner

    @classmethod
    def forbidden(cls, func):
        """Decorator for test_ functions, temporarily forbids external requests"""
        @functools.wraps(func)
        def inner(*args, **kwargs):
            with GlobalHttpCalls(False):
                return func(*args, **kwargs)

        return inner

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


class DataState:
    """Model data/files for POST/PUT requests only"""

    data = None
    json = None
    files = None
    fhandles = None

    def add_fh(self, path, dryrun):
        if _R.resolved_dryrun(dryrun):
            return path

        if self.fhandles is None:
            self.fhandles = []

        fh = open(path, mode="rb")
        self.fhandles.append(fh)
        return fh

    def complete(self, keyword_args):
        for key in ("data", "json", "files"):
            value = getattr(self, key)
            if value:
                keyword_args[key] = value

    def close(self):
        if self.fhandles:
            for f in self.fhandles:
                f.close()

    @classmethod
    def wrapped(cls, dryrun, data, json, files, filepaths):
        """
        Args:
            dryrun (bool): Optionally override current dryrun setting
            data (dict | tuple | bytes | file | None): Data to send in the body
            json: (optional) json to send in the body
            files (dict | None): File-like-objects for multipart encoding upload.
            filepaths (dict[str, Path] | None): File-like-objects for multipart encoding upload.

        Returns:
            (DataState | None): State, if needed
        """
        if data or json or files or filepaths:
            state = DataState()
            if isinstance(data, Path):
                data = state.add_fh(data, dryrun)

            state.data = data
            state.json = json
            if filepaths:
                files = {}  # Convenience / simplified multipart upload
                for k, fpath in filepaths.items():
                    files[k] = (fpath.name, state.add_fh(fpath, dryrun))

            state.files = files
            return state


class MockResponse:

    def __init__(self, status_code, content):
        self.status_code = status_code
        if content is not None and not isinstance(content, bytes):
            if not isinstance(content, str):
                content = json.dumps(content)

            content = content.encode("utf-8")

        self.content = content

    def json(self):
        return json.loads(self.text)

    @property
    def text(self):
        return stringified(self.content)


class MockedHandlerStack:

    def __init__(self):
        self.handler = None
        self.ms = None
        self.specs = {}
        self.spec_stack = []
        self.original_send_function = None

    def __repr__(self):
        name = self.handler and self.handler.__name__
        status = "active" if self.original_send_function else "stopped"
        nested = " [depth: %s]" % len(self.spec_stack) if self.spec_stack else ""
        return "%s mock %s, %s specs%s" % (name, status, len(self.specs), nested)

    def register_handler(self, handler):
        if self.handler:
            assert self.handler is handler, "Mocks targeting multiple handlers is not supported"
            return

        self.ms = handler.intercept(None)
        self.handler = handler

    def _intercept(self, *args, **kwargs):
        return self.handler.intercept(self, *args, **kwargs)

    def start(self, specs):
        if not self.spec_stack:
            assert self.original_send_function is None
            target, name = self.ms
            self.original_send_function = getattr(target, name)
            setattr(target, name, self._intercept)

        self.spec_stack.append(dict(self.specs))  # Push snapshot of current specs, to be restored by .stop()
        self.specs.update(specs)

    def stop(self):
        self.specs = self.spec_stack.pop()
        if not self.spec_stack:
            assert self.original_send_function is not None
            target, name = self.ms
            setattr(target, name, self.original_send_function)
            self.original_send_function = None

    def response_for_url(self, method, url):
        spec = self.specs.get(url)
        if spec is None:
            return MockResponse(404, dict(message="Default status code 404"))

        if isinstance(spec, BaseException):
            raise spec

        if isinstance(spec, type) and issubclass(spec, BaseException):
            raise spec("Simulated crash")

        if callable(spec):
            spec = spec(method, url)

        if isinstance(spec, MockResponse):
            return spec

        if isinstance(spec, int):
            return MockResponse(spec, "status %s" % spec)

        if isinstance(spec, tuple) and len(spec) == 2:
            return MockResponse(*spec)

        return MockResponse(200, spec)


class MockCentral:

    _stacks = {}

    @classmethod
    def get_stack(cls, handler, key):
        """Keep mock specifications stacked by decorated function, to allow stacking several mock specs per function"""
        stack = cls._stacks.get(key)
        if stack is None:
            stack = MockedHandlerStack()
            cls._stacks[key] = stack

        stack.register_handler(handler)
        return stack


class MockWrapper:
    """Intercept and mock out outgoing RestClient calls"""

    def __init__(self, handler, base_url, specs):
        self.handler = handler
        self.specs = specs or {}
        self.key = None
        self.stack = None
        if base_url:
            assert isinstance(base_url, str)
            assert isinstance(self.specs, dict)
            self.specs = {urljoin(base_url, k): v for k, v in self.specs.items()}

    def __repr__(self):
        status = "stopped" if self.stack is None else "started"
        return "%s %s, %s specs" % (self.key, status, len(self.specs))

    def start(self):
        self.stack = MockCentral.get_stack(self.handler, self.key)
        self.stack.start(self.specs)

    def stop(self):
        self.stack.stop()
        self.stack = None

    def __call__(self, func):
        """
        Args:
            func (callable): We're used as a decorator of function 'func'

        Returns:
            (callable): Decorated function
        """
        self.key = "%s.%s" % (func.__module__, func.__qualname__)

        @functools.wraps(func)
        def inner(*args, **kwargs):
            self.start()
            try:
                return func(*args, **kwargs)

            finally:
                self.stop()

        return inner

    def __enter__(self):
        """We're used as a context"""
        caller = find_caller_frame()
        self.key = "%s.%s" % (caller.f_globals.get("__name__"), caller.f_code.co_name)
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


class RestResponse:
    """Simplified response, from a typical REST query, vaguely similar to requests.Response"""

    def __init__(self, method, url, raw_response):
        """
        Args:
            method (str): Method used to query url
            url (url): Remote URL that was queried
            raw_response: Should have similar API to requests.Response
        """
        self.method = method
        self.url = url
        self.raw_response = raw_response
        self.status_code = raw_response.status_code

    def __repr__(self):
        return "<Response [%s]>" % self.status_code

    def json(self):
        return self.raw_response.json()

    @property
    def content(self):
        return self.raw_response.content

    @property
    def ok(self):
        return self.status_code and self.status_code < 400

    @property
    def text(self):
        return self.raw_response.text

    def description(self, size=1024):
        """Description showing what happened with requests 'response', fir .debug() output, or .error() reporting"""
        msg = "%s %s [%s]" % (self.method, self.url, self.status_code)
        if not self.ok and self.status_code != 404:
            msg += " %s" % self.error_reason()

        if len(msg) > size:
            msg = "%s..." % msg[:size]

        return msg

    def error_reason(self):
        """Meaningful error reason from 'response'"""
        try:
            msg = self.extract_message(self.json())
            if msg:
                return msg

        except Exception:
            pass

        return self.text

    @staticmethod
    def extract_message(data):
        """Try to get to the point of a returned REST json bit, extract meaningful message if possible"""
        if not data:
            return None

        if data and isinstance(data, str):
            return data.strip()

        if isinstance(data, dict):
            msg = RestResponse.extract_message(data.get("message"))
            if msg:
                return msg

            msg = RestResponse.extract_message(data.get("error"))
            if msg:
                return msg

            return RestResponse.extract_message(data.get("errors"))

        if isinstance(data, list):
            for item in data:
                msg = RestResponse.extract_message(item)
                if msg:
                    return msg


class RestHandler:
    """Allows to use multiple http(s) implementations"""

    @classmethod
    def mock(cls, base_url, specs=None):
        """
        Usage example:

        MY_CLIENT = RestClient("https://example.com")

        @MY_CLIENT.mock({
            "foo": {"some": "payload"}
        })
        def test_foo():
            assert MY_CLIENT.get("foo") == {"some": "payload"}

        Args:
            base (str | None): Base url (all urls in given 'spec' are relative to the base url)
            specs (dict): Map of relative url -> what to return

        Returns:
            Function decorator that will enact the mock
        """
        if callable(base_url):
            # We were invoked without arguments, form: @RestHandler.mock
            w = MockWrapper(cls, None, None)
            return w(base_url)

        return MockWrapper(cls, base_url, specs)

    @classmethod
    def is_usable(cls):
        """Is this handler currently usable"""

    @classmethod
    def new_session(cls, **session_spec):
        """New session for 'session_spec'"""

    @classmethod
    def raw_response(cls, session, method, url, **passed_through):
        """
        Args:
            session: Session as obtained via new_session() call from this handler
            method (str): Underlying method to call (GET, PUT, POST, etc)
            url (str): Absolute remote URL
            **passed_through: Passed through to underlying call
        """

    @classmethod
    def to_rest_response(cls, method, url, raw_response):
        """
        Args:
            method (str): Underlying method to call (GET, PUT, POST, etc)
            url (str): Absolute remote URL
            raw_response: Raw response as received by underlying call

        Returns:
            (RestResponse): Our simplified response object
        """

    @classmethod
    def intercept(cls, mock_caller, *_, **__):
        """
        Args:
            mock_caller (MockedHandlerStack | None): If provided: effectively intercept, if None: return target+name of function to replace
        """

    @classmethod
    def user_agent(cls):
        """Default user agent to use"""
        return "%s/%s (%s)" % (SYS_INFO.program_name, SYS_INFO.program_version, SYS_INFO.platform_info)


class RequestsHandler(RestHandler):
    """Using requests (client is to bring in the dependency)"""

    _is_usable = None

    @classmethod
    def is_usable(cls):
        if cls._is_usable is None:
            try:
                import requests
                import urllib3

                # Silence logs, we use runez' more sophisticated logging setup
                _R._runez_module().log.silence(requests, urllib3)
                cls._is_usable = True

            except ImportError:  # pragma: no cover
                cls._is_usable = False

        return cls._is_usable

    @classmethod
    def default_retry(cls):
        import urllib3

        return urllib3.Retry(backoff_factor=1, status_forcelist={413, 429, 500, 502, 503, 504})

    @classmethod
    def get_adapter(cls, retry=None):
        from requests.adapters import HTTPAdapter

        return HTTPAdapter(max_retries=retry or cls.default_retry())

    @classmethod
    def new_session(cls, http_adapter=None, https_adapter=None, retry=None):
        import requests

        session = requests.Session()
        if retry is None:
            retry = cls.default_retry()

        if retry and https_adapter is None:
            https_adapter = cls.get_adapter(retry)

        if retry and http_adapter is None:
            http_adapter = cls.get_adapter(retry)

        if https_adapter:
            session.mount("https://", https_adapter)

        if http_adapter:
            session.mount("http://", http_adapter)

        return session

    @classmethod
    def raw_response(cls, session, method, url, **passed_through):
        func = getattr(session, method.lower())
        return func(url, **passed_through)

    @classmethod
    def to_rest_response(cls, method, url, raw_response):
        return RestResponse(method, url, raw_response)

    @classmethod
    def intercept(cls, mock_caller, *args, **__):
        if mock_caller is None:
            from requests.adapters import HTTPAdapter

            return HTTPAdapter, "send"

        from requests import Response

        request = args[0]
        mocked = mock_caller.response_for_url(request.method, request.url)
        r = Response()
        r.encoding = "utf-8"
        r.status_code = mocked.status_code
        r.url = request.url
        r.request = request
        r._content = mocked.content
        return r

    @classmethod
    def user_agent(cls):
        import requests

        return "%s requests/%s" % (super().user_agent(), requests.__version__)


class RestClient:
    """REST client with good defaults for retry, timeout, ... + support for --dryrun mode etc"""

    handler = RequestsHandler

    def __init__(self, base_url=None, headers=None, timeout=30, user_agent=None, handler=None, session=None, **session_spec):
        """
        Args:
            base_url (str | None): Base url of remote REST server
            headers (dict | None): Default headers to use
            timeout (int): Default timeout in seconds
            user_agent (str | None): User-Agent to use for outgoing calls coming from this client (default: handler.user_agent())
            handler: Optional: override default handler
            session: Optional: override getting handler.new_session()
        """
        self.base_url = base_url
        self.headers = dict(headers) if headers else {}
        self.timeout = timeout
        if handler:
            self.handler = handler

        if not self.handler or not self.handler.is_usable():
            raise Exception("RestClient handler '%s' is not usable" % self.handler)

        self.user_agent = user_agent or self.handler.user_agent()
        self.session = session or self.handler.new_session(**session_spec)
        if self.user_agent:
            self.headers["User-Agent"] = self.user_agent

    def __repr__(self):
        return stringified(self.base_url or self.session)

    def sub_client(self, relative_url):
        """
        Args:
            relative_url (str): Relative url (relative to self.base_url)

        Returns:
            (RestClient): Same as current client, with a different/child base url
        """
        url = urljoin(self.base_url, relative_url)
        return RestClient(
            url, headers=self.headers, timeout=self.timeout, user_agent=self.user_agent, handler=self.handler, session=self.session
        )

    def full_url(self, url):
        """
        Args:
            url (str): Relative URL

        Returns:
            (str): Absolute URL, auto-completed with `self.base_url`
        """
        return urljoin(self.base_url, url)

    def download(self, url, destination, fatal=True, logger=UNSET, dryrun=UNSET, params=None, headers=None):
        """
        Args:
            url (str): URL of resource to download (may be absolute, or relative to self.base_url)
            destination (str | Path): Path to local file where to store the download
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request

        Returns:
            (RestResponse): Response from underlying call
        """
        response = self._get_response("GET", url, fatal, logger, dryrun=dryrun, params=params, headers=headers, action="download")
        if response.ok and not _R.resolved_dryrun(dryrun):
            with open(destination, "wb") as fh:
                fh.write(response.content)

        return response

    def untar(self, url, destination, fatal=True, logger=UNSET, dryrun=UNSET, params=None, headers=None):
        """
        Args:
            url (str): URL of .tar.gz to unpack (may be absolute, or relative to self.base_url)
            destination (str | Path): Path to local folder where to untar url
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request

        Returns:
            (RestResponse): Response from underlying call
        """
        destination = to_path(destination).absolute()
        with TempFolder():
            tarball_path = to_path(os.path.basename(url)).absolute()
            response = self.download(url, tarball_path, fatal=fatal, logger=logger, dryrun=dryrun, params=params, headers=headers)
            if response.ok:
                untar(tarball_path, destination, fatal=fatal, logger=logger, dryrun=dryrun)

            return response

    def get_response(self, url, fatal=True, logger=UNSET, params=None, headers=None):
        """
        Args:
            url (str): Remote URL (may be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request

        Returns:
            (RestResponse): Response from underlying call
        """
        return self._get_response("GET", url, fatal, logger, params=params, headers=headers)

    def delete(self, url, fatal=True, logger=UNSET, dryrun=UNSET, params=None, headers=None):
        """Same as underlying .delete(), but respecting 'dryrun' mode

        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request

        Returns:
            (RestResponse): Response from underlying call
        """
        return self._get_response("DELETE", url, fatal, logger, dryrun=dryrun, params=params, headers=headers)

    def get(self, url, fatal=True, logger=UNSET, params=None, headers=None):
        """
        Args:
            url (str): Remote URL (may be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request

        Returns:
            (dict | None): Deserialized .json() from response, if available
        """
        response = self.get_response(url, fatal=fatal, logger=logger, params=params, headers=headers)
        if response.ok:
            return response.json()

    def head(self, url, fatal=True, logger=UNSET, params=None, headers=None):
        """
        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request

        Returns:
            (RestResponse): Response from underlying call
        """
        return self._get_response("HEAD", url, fatal, logger, params=params, headers=headers)

    def post(
        self, url, fatal=True, logger=UNSET, dryrun=UNSET, params=None, headers=None, data=None, json=None, files=None, filepaths=None
    ):
        """Same as underlying .post(), but respecting 'dryrun' mode

        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request
            data (dict | tuple | bytes | file | None): Data to send in the body
            json: (optional) json to send in the body
            files (dict | None): File-like-objects for multipart encoding upload.
            filepaths (dict[str, Path] | None): File-like-objects for multipart encoding upload.

        Returns:
            (RestResponse): Response from underlying call
        """
        state = DataState.wrapped(dryrun, data, json, files, filepaths)
        return self._get_response("POST", url, fatal, logger, dryrun=dryrun, params=params, headers=headers, state=state)

    def put(self, url, fatal=True, logger=UNSET, dryrun=UNSET, params=None, headers=None, data=None, json=None, files=None, filepaths=None):
        """
        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request
            data (dict | tuple | bytes | file | None): Data to send in the body
            json: (optional) json to send in the body
            files (dict | None): File-like-objects for multipart encoding upload.
            filepaths (dict[str, Path] | None): File-like-objects for multipart encoding upload.

        Returns:
            (RestResponse): Response from underlying call
        """
        state = DataState.wrapped(dryrun, data, json, files, filepaths)
        return self._get_response("PUT", url, fatal, logger, dryrun=dryrun, params=params, headers=headers, state=state)

    def url_exists(self, url, logger=False):
        """
        Args:
            url (str): URL to query (can be absolute, or relative to self.base_url)
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter

        Returns:
            (bool): True if remote URL exists (ie: not a 404)
        """
        response = self.head(url, fatal=False, logger=logger)
        return bool(response and response.ok)

    def mock(self, specs):
        """
        Usage example:

        MY_CLIENT = RestClient("https://example.com")

        @MY_CLIENT.mock({
            "foo": {"some": "payload"}
        })
        def test_foo():
            assert MY_CLIENT.get("foo") == {"some": "payload"}

        Args:
            specs (dict): Map of relative url -> what to return

        Returns:
            Function decorator that will enact the mock
        """
        if callable(specs):
            # We were invoked without arguments, form: @MY_CLIENT.mock
            w = MockWrapper(self.handler, self.base_url, None)
            return w(specs)

        return MockWrapper(self.handler, self.base_url, specs)

    def _get_response(self, method, url, fatal, logger, dryrun=False, params=None, headers=None, state=None, action=None):
        """
        Args:
            method (str): Underlying method to call
            url (str): Remote URL (may be absolute, or relative to self.base_url)
            fatal (bool | None): True: abort execution on failure, False: don't abort but log, None: don't abort, don't log
            logger (callable | bool | None): Logger to use, True to print(), False to trace(), None to disable log chatter
            dryrun (bool): Optionally override current dryrun setting
            params (dict | None): Key/value pairs for query string
            headers (dict | None): Optional Headers specific to this request
            state (DataState | None): For PUT/POST requests
            action (str | None): Action to refer to in dryrun message (default: method)

        Returns:
            (RestResponse): Response from underlying call
        """
        absolute_url = self.full_url(url)
        message = "%s %s" % (action or method, absolute_url)
        if _R.hdry(dryrun, logger, message):
            return RestResponse(method, absolute_url, MockResponse(200, dict(message="dryrun %s" % message)))

        full_headers = self.headers
        if headers:
            full_headers = dict(full_headers)
            full_headers.update(headers)

        keyword_args = dict(headers=full_headers, timeout=self.timeout)
        if state is not None:
            state.complete(keyword_args)

        try:
            raw_response = self.handler.raw_response(self.session, method, absolute_url, **keyword_args)
            response = self.handler.to_rest_response(method, absolute_url, raw_response)
            if fatal or logger is not None:
                msg = response.description()
                if fatal and not response.ok:
                    abort(msg)

                _R.hlog(logger, msg)

            return response

        finally:
            if state is not None:
                state.close()
