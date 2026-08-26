"""Engine resource limits.

Bounded responses are a hard requirement: every operation caps how much data it
returns so a single call can never blow up the response, the LLM context, or
memory.  Defaults live here; the backend can override them from configuration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineLimits:
    # read_file
    max_read_bytes: int = 64 * 1024  # bytes returned by a single read_file call
    max_readable_file_bytes: int = 2 * 1024 * 1024  # refuse whole-file reads above this
    # list_files
    default_page_size: int = 200
    max_page_size: int = 1000
    # search_code
    max_search_results: int = 100
    max_search_per_file: int = 20
    max_search_filesize: int = 1024 * 1024  # skip files larger than this when searching
    search_timeout_s: float = 15.0
    max_query_length: int = 1000
    # shared
    max_line_length: int = 2000  # truncate individual lines in previews
    binary_sniff_bytes: int = 8192
    walk_file_cap: int = 20000  # hard cap on files visited during a fallback walk
    # GitHub search: cap how many blobs a single search fetches over the network,
    # so an unauthenticated call cannot exhaust the API rate limit. Coverage
    # beyond this is reported as truncated with a note (never silently dropped).
    github_search_max_files: int = 300


DEFAULT_LIMITS = EngineLimits()
