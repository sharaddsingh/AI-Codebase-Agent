"""Tool specifications and dispatch for the agent.

Two things live here:

1. :data:`TOOL_SCHEMAS` — the tool JSON schemas in OpenAI function format; each
   model adapter converts them to its provider (e.g. Anthropic ``input_schema``).
   The repository is *not* a tool parameter: the loop binds a single
   :class:`~code_intelligence.repository.RepositoryInterface` for the whole run,
   so the model can never point a tool at another repo (scope is enforced by us,
   not requested by the model).

2. :func:`execute_tool` — dispatch a model-requested tool call against that
   repository, returning a bounded, JSON-serializable payload plus structured
   *evidence* (which files were touched, which concrete line ranges were read).
   The loop uses the evidence for budget accounting and citation validation.

Every failure is converted into a small ``{"error", "message"}`` payload rather
than raised, so the model observes the failure and can adapt (e.g. pick a
different path) instead of the run aborting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from code_intelligence.errors import CodeIntelError
from code_intelligence.repository import RepositoryInterface

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Fast lexical (text/regex) search across the repository's files. "
                "Use this first to locate where a symbol, string, endpoint, or "
                "error message appears. Returns matching lines with file paths and "
                "line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The text or regular expression to search for.",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "Treat query as a regular expression (default false).",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Case-sensitive match (default false).",
                    },
                    "path_glob": {
                        "type": "string",
                        "description": "Optional glob to restrict files, e.g. '**/*.py'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List the entries (files and subdirectories) of a directory in the "
                "repository. Use path='' for the repository root. Ignored paths "
                "(.git, node_modules, build output, etc.) are omitted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repo-relative directory path; '' for the root.",
                    },
                    "page": {"type": "integer", "description": "1-based page number."},
                    "page_size": {"type": "integer", "description": "Entries per page."},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a bounded slice of a text file. Prefer a specific line window "
                "(start_line/end_line) over reading the whole file. Line numbers are "
                "1-based and inclusive. Binary and oversized files are refused."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative file path."},
                    "start_line": {
                        "type": "integer",
                        "description": "1-based first line to read (optional).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "1-based last line to read, inclusive (optional).",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_metadata",
            "description": (
                "Return metadata for a file: size in bytes, line count, detected "
                "language, whether it looks binary, and a content hash. Cheap way to "
                "check a file before reading it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative file path."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_NAMES: frozenset[str] = frozenset(t["function"]["name"] for t in TOOL_SCHEMAS)


@dataclass
class ToolExecution:
    name: str
    arguments: dict
    ok: bool
    payload: dict
    summary: str
    files: list[str] = field(default_factory=list)  # files this call touched
    ranges: list[tuple[str, int, int]] = field(default_factory=list)  # (path, start, end)
    error: str | None = None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return default


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def execute_tool(repo: RepositoryInterface, name: str, arguments: dict) -> ToolExecution:
    """Dispatch a single tool call against ``repo``. Never raises for tool-level
    problems; converts :class:`CodeIntelError` into an error payload the model can see."""

    args = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "search_code":
            return _do_search(repo, args)
        if name == "list_files":
            return _do_list(repo, args)
        if name == "read_file":
            return _do_read(repo, args)
        if name == "get_file_metadata":
            return _do_metadata(repo, args)
        return ToolExecution(
            name=name,
            arguments=args,
            ok=False,
            payload={"error": "unknown_tool", "message": f"Unknown tool '{name}'."},
            summary=f"unknown tool '{name}'",
            error="unknown_tool",
        )
    except CodeIntelError as exc:
        return ToolExecution(
            name=name,
            arguments=args,
            ok=False,
            payload={"error": exc.code, "message": exc.message},
            summary=f"error ({exc.code}): {exc.message}",
            error=exc.code,
        )


def _do_search(repo: RepositoryInterface, args: dict) -> ToolExecution:
    query = _as_str(args.get("query")) or ""
    results = repo.search_code(
        query,
        regex=_as_bool(args.get("regex")),
        case_sensitive=_as_bool(args.get("case_sensitive")),
        path_glob=_as_str(args.get("path_glob")),
        max_results=_as_int(args.get("max_results")),
    )
    touched = sorted({m.path for m in results.matches})
    trunc = " (truncated)" if results.truncated else ""
    summary = (
        f"{results.total_matches} match(es) for {query!r} via {results.engine}"
        f"{trunc}; files: {', '.join(touched[:8]) or 'none'}"
    )
    return ToolExecution(
        name="search_code",
        arguments=args,
        ok=True,
        payload=results.model_dump(mode="json"),
        summary=summary,
        files=touched,
    )


def _do_list(repo: RepositoryInterface, args: dict) -> ToolExecution:
    path = _as_str(args.get("path")) or ""
    listing = repo.list_files(
        path,
        page=_as_int(args.get("page")) or 1,
        page_size=_as_int(args.get("page_size")),
    )
    summary = (
        f"{listing.total} entr{'y' if listing.total == 1 else 'ies'} in "
        f"{path or '<root>'!r} (page {listing.page})"
    )
    return ToolExecution(
        name="list_files",
        arguments=args,
        ok=True,
        payload=listing.model_dump(mode="json"),
        summary=summary,
    )


def _do_read(repo: RepositoryInterface, args: dict) -> ToolExecution:
    path = _as_str(args.get("path")) or ""
    content = repo.read_file(
        path,
        start_line=_as_int(args.get("start_line")),
        end_line=_as_int(args.get("end_line")),
    )
    trunc = " (truncated)" if content.truncated else ""
    summary = (
        f"read {content.path}:{content.start_line}-{content.end_line} "
        f"of {content.total_lines} lines{trunc}"
    )
    return ToolExecution(
        name="read_file",
        arguments=args,
        ok=True,
        payload=content.model_dump(mode="json"),
        summary=summary,
        files=[content.path],
        ranges=[(content.path, content.start_line, content.end_line)],
    )


def _do_metadata(repo: RepositoryInterface, args: dict) -> ToolExecution:
    path = _as_str(args.get("path")) or ""
    meta = repo.get_file_metadata(path)
    summary = (
        f"{meta.path}: {meta.size_bytes} bytes, {meta.line_count} lines, "
        f"{meta.language or 'unknown'}{', binary' if meta.is_binary else ''}"
    )
    return ToolExecution(
        name="get_file_metadata",
        arguments=args,
        ok=True,
        payload=meta.model_dump(mode="json"),
        summary=summary,
    )
