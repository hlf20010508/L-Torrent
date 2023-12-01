import asyncio
import traceback
import sys
from yarl._url import URL
from yarl import _quoting_py
from typing import (
    Any,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Type,
    Union,
    cast,
)
from aiohttp import http
from aiohttp.client_reqrep import ClientRequest, ClientResponse, Fingerprint, _CONTAINS_CONTROL_CHAR_RE
from aiohttp.client import ClientSession
from aiohttp.tracing import Trace
from aiohttp.typedefs import (
    LooseCookies,
    LooseHeaders,
)

from aiohttp.helpers import (
    BaseTimerContext,
    BasicAuth,
    TimerNoop,
)

try:
    from ssl import SSLContext
except ImportError:  # pragma: no cover
    ssl = None  # type: ignore[assignment]
    SSLContext = object  # type: ignore[misc,assignment]

def ClientRequest__init__(
    self,
    method: str,
    url: URL,
    *,
    params: Optional[Mapping[str, str]] = None,
    headers: Optional[LooseHeaders] = None,
    skip_auto_headers: Iterable[str] = frozenset(),
    data: Any = None,
    cookies: Optional[LooseCookies] = None,
    auth: Optional[BasicAuth] = None,
    version: http.HttpVersion = http.HttpVersion11,
    compress: Optional[str] = None,
    chunked: Optional[bool] = None,
    expect100: bool = False,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    response_class: Optional[Type["ClientResponse"]] = None,
    proxy: Optional[URL] = None,
    proxy_auth: Optional[BasicAuth] = None,
    timer: Optional[BaseTimerContext] = None,
    session: Optional["ClientSession"] = None,
    ssl: Union[SSLContext, Literal[False], Fingerprint, None] = None,
    proxy_headers: Optional[LooseHeaders] = None,
    traces: Optional[List["Trace"]] = None,
    trust_env: bool = False,
    server_hostname: Optional[str] = None,
):
    if loop is None:
        loop = asyncio.get_event_loop()

    match = _CONTAINS_CONTROL_CHAR_RE.search(method)
    if match:
        raise ValueError(
            f"Method cannot contain non-token characters {method!r} "
            "(found at least {match.group()!r})"
        )

    assert isinstance(url, URL), url
    assert isinstance(proxy, (URL, type(None))), proxy
    # FIXME: session is None in tests only, need to fix tests
    # assert session is not None
    self._session = cast("ClientSession", session)
    if params:
        url = url.with_query(params)
        
    self.original_url = url
    self.url = url.with_fragment(None)
    self.method = method.upper()
    self.chunked = chunked
    self.compress = compress
    self.loop = loop
    self.length = None
    if response_class is None:
        real_response_class = ClientResponse
    else:
        real_response_class = response_class
    self.response_class: Type[ClientResponse] = real_response_class
    self._timer = timer if timer is not None else TimerNoop()
    self._ssl = ssl
    self.server_hostname = server_hostname

    if loop.get_debug():
        self._source_traceback = traceback.extract_stack(sys._getframe(1))

    self.update_version(version)
    self.update_host(url)
    self.update_headers(headers)
    self.update_auto_headers(skip_auto_headers)
    self.update_cookies(cookies)
    self.update_content_encoding(data)
    self.update_auth(auth, trust_env)
    self.update_proxy(proxy, proxy_auth, proxy_headers)

    self.update_body_from_data(data)
    if data is not None or self.method not in self.GET_METHODS:
        self.update_transfer_encoding()
    self.update_expect_continue(expect100)
    if traces is None:
        traces = []
    self._traces = traces


URL._QUERY_PART_QUOTER = _quoting_py._Quoter(safe="%?/:@", qs=True, requote=True)
ClientRequest.__init__ = ClientRequest__init__
