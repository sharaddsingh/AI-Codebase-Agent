"""A synchronous facade over the **official GitHub MCP server**.

The rest of the application below :class:`~code_intelligence.repository.RepositoryInterface`
is synchronous, but an MCP :class:`~mcp.Client` is asyncio.  :class:`GitHubMCPClient`
bridges the two: it owns a **dedicated daemon thread running one persistent asyncio
event loop**, opens **one** long-lived MCP session over that loop, and exposes a
blocking ``call_tool`` / ``list_tools`` / ``close`` surface that other threads
(each FastAPI/SSE request runs on its own worker thread) call safely via
``asyncio.run_coroutine_threadsafe``.

Design invariants
-----------------
* **One session, shared.** ``owner``/``repo`` are tool *arguments*, so a single
  session serves every GitHub repository — no subprocess or connection per read.
* **The runner task both enters and exits the session.** anyio task groups forbid
  exiting a cancel scope in a different task than entered it, so a single
  ``_runner`` coroutine opens the :class:`~contextlib.AsyncExitStack`, keeps it
  open until :meth:`close`, and unwinds it in that same task.  Individual tool
  calls run as *separate* coroutines against the already-open session (anyio
  memory streams are task-safe).
* **Read-only, fail-closed.** After ``initialize``/``list_tools`` the client
  asserts the server advertises **no** write tool and **does** advertise the read
  tools we depend on; otherwise it raises and refuses to serve the session.
* **The token never leaks.** It lives only on the transport's HTTP default
  headers.  It is never logged, never placed in ``repr``, and never included in
  an exception message; error messages are generic and omit raw response bodies.
"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from .errors import (
    CodeIntelError,
    GitHubMCPAuthError,
    GitHubMCPConnectionError,
    GitHubMCPToolError,
    GitHubMCPUnavailableError,
    GitHubRepoAccessDeniedError,
    GitHubRepoNotFoundError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# Tools the official server exposes only when write access is enabled.  If any of
# these appear while we requested read-only mode, we refuse the session entirely.
_WRITE_TOOLS = frozenset(
    {
        "create_branch",
        "create_or_update_file",
        "create_repository",
        "delete_file",
        "delete_repository",
        "fork_repository",
        "push_files",
        "create_issue",
        "update_issue",
        "add_issue_comment",
        "create_pull_request",
        "update_pull_request",
        "merge_pull_request",
        "create_pull_request_review",
        # Generic write verbs, defended against regardless of server naming.
        "write_file",
        "create_file",
        "update_file",
        "push",
        "commit",
    }
)

# Read tools :class:`GitHubMCPRepository` relies on.  Missing any of them means the
# server was configured without the toolsets we need — fail closed with a clear error.
_REQUIRED_READ_TOOLS = frozenset(
    {"list_commits", "get_repository_tree", "get_file_contents", "search_code"}
)

_AUTH_MSG = (
    "The GitHub MCP server rejected the request. Set a valid server-side "
    "GITHUB_TOKEN with read access (the remote server requires a token even for "
    "public repositories)."
)
_NOT_FOUND_MSG = (
    "The GitHub repository, path, or ref was not found (or is not visible to the "
    "configured token)."
)
_DENIED_MSG = "The configured GitHub token is not permitted to access this repository."


# --------------------------------------------------------------------------- #
# Transport seam                                                              #
# --------------------------------------------------------------------------- #
class MCPTransport(Protocol):
    """A way to obtain a connected, initialized :class:`~mcp.Client`.

    ``open`` is an async context manager that yields an *entered* client and
    tears it down on exit.  ``describe`` returns a short, secret-free label for
    diagnostics (never the token).
    """

    def open(self) -> Any:  # returns an async context manager yielding a Client
        ...

    def describe(self) -> str:
        ...


class RemoteHttpTransport:
    """Streamable-HTTP transport to the official remote GitHub MCP server.

    Auth, toolset selection, and read-only mode are conveyed as HTTP headers on a
    prebuilt ``httpx2.AsyncClient`` (``streamable_http_client`` takes no
    ``headers=`` kwarg).  We own that HTTP client, so we close it ourselves after
    the MCP session unwinds.
    """

    def __init__(
        self,
        url: str,
        *,
        token: str | None,
        toolsets: str,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._token = token
        self._toolsets = toolsets
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-MCP-Toolsets": self._toolsets,
            "X-MCP-Readonly": "true",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @asynccontextmanager
    async def open(self) -> AsyncIterator[Client]:
        import httpx2  # type: ignore[import-untyped]  # local import: only prod path needs it

        http_client = httpx2.AsyncClient(headers=self._headers(), timeout=self._timeout)
        try:
            transport = streamable_http_client(self._url, http_client=http_client)
            async with Client(transport) as client:
                yield client
        finally:
            await http_client.aclose()

    def describe(self) -> str:
        # The endpoint URL is not a secret; the token is never included.
        return f"remote:{self._url} toolsets={self._toolsets}"


class InProcessTransport:
    """Test transport: connect an in-memory :class:`~mcp.Client` to a server object
    (e.g. an :class:`mcp.server.mcpserver.MCPServer`) with no network."""

    def __init__(self, server: Any, *, label: str = "in-process") -> None:
        self._server = server
        self._label = label

    @asynccontextmanager
    async def open(self) -> AsyncIterator[Client]:
        async with Client(self._server) as client:
            yield client

    def describe(self) -> str:
        return self._label


# --------------------------------------------------------------------------- #
# Tool result wrapper                                                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MCPToolResult:
    """A successful (``is_error=False``) tool result, decoupled from the SDK type.

    ``content`` holds the raw content blocks (``TextContent`` /
    ``EmbeddedResource`` / ``ResourceLink`` / …) so callers that need bytes (file
    reads) can inspect them, while :meth:`json` covers the common data-tool case.
    """

    tool: str
    content: tuple[Any, ...]
    structured: Any = None

    def json(self) -> Any:
        texts = [b.text for b in self.content if isinstance(b, TextContent)]
        if len(texts) == 1:
            return _parse_json(texts[0], self.tool)
        if len(texts) > 1:
            return [_parse_json(t, self.tool) for t in texts]
        if self.structured is not None:
            return self.structured
        return {}


def _parse_json(text: str, tool: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise GitHubMCPToolError(
            f"The GitHub MCP tool {tool!r} returned a response that could not be parsed."
        ) from exc


# --------------------------------------------------------------------------- #
# The client                                                                  #
# --------------------------------------------------------------------------- #
class GitHubMCPClient:
    """Blocking facade over one persistent, read-only GitHub MCP session."""

    def __init__(self, transport: MCPTransport, *, timeout: float = 30.0) -> None:
        self._transport = transport
        self._call_timeout = timeout
        self._connect_timeout = timeout + 10.0

        self._state_lock = threading.Lock()
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: Client | None = None
        self._shutdown: asyncio.Event | None = None
        self._tool_names: tuple[str, ...] = ()
        self._connect_error: BaseException | None = None
        self._closed = False

    # -- public sync surface ---------------------------------------------- #
    def connect(self) -> None:
        """Establish the session if needed (idempotent, thread-safe)."""

        with self._state_lock:
            if self._client is not None:
                return
            if self._closed:
                raise GitHubMCPConnectionError("The GitHub MCP client has been closed.")
            bringing_up = self._thread is not None and self._thread.is_alive()
            if not bringing_up:
                self._ready.clear()
                self._connect_error = None
                self._thread = threading.Thread(
                    target=self._thread_main, name="github-mcp", daemon=True
                )
                self._thread.start()

        if not self._ready.wait(timeout=self._connect_timeout):
            raise GitHubMCPConnectionError("Timed out establishing a GitHub MCP session.")
        if self._connect_error is not None:
            raise _as_public_error(self._connect_error, context="connect")

    def list_tools(self) -> list[str]:
        self.connect()
        return list(self._tool_names)

    def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None, *, timeout: float | None = None
    ) -> MCPToolResult:
        self.connect()
        loop, client = self._loop, self._client
        if loop is None or client is None:  # pragma: no cover - connect() guarantees these
            raise GitHubMCPConnectionError("The GitHub MCP session is not connected.")

        future = asyncio.run_coroutine_threadsafe(
            client.call_tool(name, arguments or {}), loop
        )
        try:
            result = future.result(timeout=timeout or self._call_timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise GitHubMCPToolError(f"The GitHub MCP tool {name!r} timed out.") from None
        except CodeIntelError:
            raise
        except BaseException as exc:  # noqa: BLE001 - translated to a safe public error
            raise _as_public_error(exc, context="tool", tool=name) from None

        if result.is_error:
            raise _error_from_result(result, tool=name)
        return MCPToolResult(
            tool=name,
            content=tuple(result.content),
            structured=result.structured_content,
        )

    def close(self) -> None:
        """Signal the loop to unwind the session and stop the thread (idempotent)."""

        with self._state_lock:
            self._closed = True
            thread, loop, shutdown = self._thread, self._loop, self._shutdown
        if thread is None:
            return
        if loop is not None and shutdown is not None:
            try:
                loop.call_soon_threadsafe(shutdown.set)
            except RuntimeError:
                pass  # loop already stopped
        thread.join(timeout=10.0)
        with self._state_lock:
            self._client = None
            self._thread = None

    # -- loop thread internals -------------------------------------------- #
    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._runner())
        except BaseException as exc:  # noqa: BLE001 - surfaced to connect() via _connect_error
            if self._connect_error is None:
                self._connect_error = exc
            self._ready.set()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            loop.close()
            self._loop = None

    async def _runner(self) -> None:
        self._shutdown = asyncio.Event()
        try:
            async with AsyncExitStack() as stack:
                client = await stack.enter_async_context(self._transport.open())
                listed = await client.list_tools()
                names = tuple(t.name for t in listed.tools)
                _assert_read_only(names)
                self._client = client
                self._tool_names = names
                self._ready.set()  # only signal success once the session is live
                await self._shutdown.wait()  # hold the session open until close()
        except BaseException as exc:  # noqa: BLE001 - reported to connect() as _connect_error
            self._client = None
            if self._connect_error is None:
                self._connect_error = exc
            raise
        finally:
            self._ready.set()  # never let connect() hang, even on failure

    def __repr__(self) -> str:
        return (
            f"<GitHubMCPClient transport={self._transport.describe()!r} "
            f"connected={self._client is not None}>"
        )


# --------------------------------------------------------------------------- #
# Read-only assertion + error translation                                     #
# --------------------------------------------------------------------------- #
def _assert_read_only(names: tuple[str, ...]) -> None:
    advertised = set(names)
    writes = sorted(advertised & _WRITE_TOOLS)
    if writes:
        raise GitHubMCPUnavailableError(
            "The GitHub MCP server advertised write-capable tools while read-only "
            "mode was requested; refusing to proceed. Configure the server in "
            "read-only mode."
        )
    missing = sorted(_REQUIRED_READ_TOOLS - advertised)
    if missing:
        raise GitHubMCPUnavailableError(
            "The GitHub MCP server is missing required read-only tools; it cannot "
            "be used to investigate repositories. Check the configured toolsets."
        )


def _texts(content: Any) -> str:
    return " ".join(b.text for b in content if isinstance(b, TextContent))


def _error_from_result(result: Any, *, tool: str) -> CodeIntelError:
    """Map an ``is_error`` tool result to a typed, secret-free error.

    Classification scans the server's message for well-known signals but never
    echoes that raw message back to the user.
    """

    text = _texts(result.content).lower()
    if any(s in text for s in ("401", "unauthorized", "bad credentials", "authentication")):
        return GitHubMCPAuthError(_AUTH_MSG)
    if any(s in text for s in ("rate limit", "rate-limit", "secondary rate", "429")):
        return GitHubMCPToolError(
            "GitHub rate-limited the request through the MCP server; please retry shortly."
        )
    if any(s in text for s in ("404", "not found", "could not resolve", "no commit found")):
        return GitHubRepoNotFoundError(_NOT_FOUND_MSG)
    if any(s in text for s in ("403", "forbidden", "access denied", "permission")):
        return GitHubRepoAccessDeniedError(_DENIED_MSG)
    return GitHubMCPToolError(f"The GitHub MCP tool {tool!r} returned an error.")


def _flatten(exc: BaseException) -> list[BaseException]:
    inner = getattr(exc, "exceptions", None)
    if inner:
        out: list[BaseException] = []
        for e in inner:
            out.extend(_flatten(e))
        return out
    return [exc]


def _as_public_error(
    exc: BaseException, *, context: str, tool: str | None = None
) -> CodeIntelError:
    leaves = _flatten(exc)
    for e in leaves:
        if isinstance(e, CodeIntelError):
            return e
    blob = " ; ".join(f"{type(e).__name__}: {e}" for e in leaves).lower()
    if any(s in blob for s in ("401", "unauthorized", "bad credentials", "authentication", "403", "forbidden")):
        return GitHubMCPAuthError(_AUTH_MSG)
    if context == "connect":
        return GitHubMCPConnectionError(
            "Could not connect to the GitHub MCP server. Check network access and "
            "that GITHUB_TOKEN is set."
        )
    return GitHubMCPToolError(
        f"The GitHub MCP tool {tool!r} failed." if tool else "A GitHub MCP call failed."
    )
