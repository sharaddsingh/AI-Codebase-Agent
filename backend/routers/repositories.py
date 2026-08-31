"""Repository registration, upload, listing, and removal.

Two ways to register a repository:

* ``POST /api/repositories/upload`` — multipart upload of a folder chosen in
  the browser. The files are streamed to disk under the configured upload
  root, then registered as a :class:`LocalRepositoryAdapter`.
* ``POST /api/repositories/github`` — JSON body with a GitHub URL. The
  repository is read over the official GitHub MCP server (read-only).

There is **no** path-input endpoint: the backend never accepts a
user-supplied filesystem path. Browsers pick folders via the File System
Access API / drag-and-drop and we own the on-disk target.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from code_intelligence.errors import RegistrationError, UploadTooLargeError
from code_intelligence.models import RepositoryInfo, RepositoryKind

from ..deps import get_registry, get_upload_root, upload_limits
from ..schemas import GitHubRegisterRequest
from ..uploaded_repos import (
    UploadLimits,
    cleanup_uploaded_repo,
    sanitize_repo_name,
    save_upload,
    write_upload_meta,
)
from ..github_repos_state import forget_github_repo, record_github_repo

log = logging.getLogger("backend.repositories")

router = APIRouter(prefix="/repositories", tags=["repositories"])

# The upload endpoint parses its own multipart body instead of declaring
# ``files: list[UploadFile] = File(...)``. FastAPI would call
# ``Request.form()`` with Starlette's defaults, and one of those defaults is
# ``max_files=1000`` — a hard 400 ("Too many files") that fires before our own
# limits are ever consulted, so the documented per-upload file cap was
# unreachable and a mid-sized folder failed with a confusing error. There is no
# FastAPI-level knob for it, so we drive the parser ourselves.
#
# Only ``files`` and ``name`` are expected, so the field allowance stays tiny.
# ``max_part_size`` bounds *non-file* parts only (Starlette streams file parts
# to a spooled temp file), which here means it bounds ``name`` and nothing else.
_MAX_FORM_FIELDS = 16
_MAX_FIELD_BYTES = 64 * 1024

# Per-part multipart framing: headers, boundary, and the filename. Allowed on
# top of the byte cap so the Content-Length pre-check below rejects only bodies
# that are genuinely too big, not ones that are merely made of many small files.
_PART_OVERHEAD_BYTES = 512

_UPLOAD_OPENAPI_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                            "description": "Folder contents, one multipart part per file. "
                            "Each part's filename is the repo-relative path.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Display name (the picked folder's own name).",
                        },
                    },
                    "required": ["files"],
                }
            }
        },
    }
}


async def _parse_upload_form(
    request: Request, limits: UploadLimits
) -> tuple[list[UploadFile], str | None]:
    """Read the multipart body under *our* limits rather than Starlette's.

    Returns ``(file_parts, display_name)``. Raises
    :class:`RegistrationError` for a body we cannot read and
    :class:`UploadTooLargeError` when the declared size is over the cap.
    """

    if "multipart/form-data" not in request.headers.get("content-type", "").lower():
        raise RegistrationError("Upload must be sent as multipart/form-data.")

    # Refuse an oversized body from its declared length, before reading it.
    # save_upload enforces the same cap authoritatively while writing, but only
    # after the parser has buffered every part — so without this check a huge
    # folder is fully spooled to disk just to be rejected.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        allowance = limits.max_total_bytes + limits.max_files * _PART_OVERHEAD_BYTES
        if int(declared) > allowance:
            raise UploadTooLargeError(
                f"Upload is larger than the {limits.max_total_bytes // (1024 * 1024)} MB limit."
            )

    parser = MultiPartParser(
        request.headers,
        request.stream(),
        max_files=limits.max_files,
        max_fields=_MAX_FORM_FIELDS,
        max_part_size=_MAX_FIELD_BYTES,
    )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        # Covers a malformed body and our own raised limits (too many files).
        raise RegistrationError(f"Could not read the upload: {exc.message}") from exc

    files = [part for part in form.getlist("files") if isinstance(part, UploadFile)]
    name = form.get("name")
    return files, name if isinstance(name, str) else None

@router.post(
    "/upload",
    response_model=RepositoryInfo,
    status_code=201,
    openapi_extra=_UPLOAD_OPENAPI_BODY,
)
async def upload_repository(request: Request) -> RepositoryInfo:
    """Stream a browser-picked folder into the upload root and register it.

    Every part's ``filename`` is treated as a repo-relative path; the upload
    pipeline enforces containment, ignore-dir, and size limits. On any
    failure the partial directory is wiped before the error is returned so a
    half-uploaded repo never lingers on disk.

    ``name`` is display-only and never touches the filesystem — the on-disk
    directory is always the server-generated repo id. It exists so the UI can
    show "my-project" instead of "up_3f0a…"; when it is missing or unusable we
    fall back to that directory name. It is also written to a sidecar beside
    the directory so it survives a backend restart.
    """

    limits = upload_limits()
    files, raw_name = await _parse_upload_form(request, limits)
    if not files:
        raise RegistrationError("Upload contained no files.")

    upload_root = get_upload_root()
    _repo_dir_name, repo_dir, _written = save_upload(upload_root, files, limits=limits)
    display = sanitize_repo_name(raw_name) or Path(repo_dir).name
    write_upload_meta(upload_root, repo_dir, display)
    info = get_registry().register_uploaded(Path(repo_dir), name=display)
    log.info("uploaded repo registered", extra={"extra": {"repo_id": info.id}})
    return info


@router.post("/github", response_model=RepositoryInfo, status_code=201)
def register_github_repository(body: GitHubRegisterRequest) -> RepositoryInfo:
    """Register a GitHub repository by URL (read-only, MCP-backed).

    A bad URL raises :class:`InvalidGitHubUrlError`, which the global error
    handler maps to a 400 with the standard ``{"error": {"code", "message"}}``
    envelope.
    """

    info = get_registry().register_github(body.url, name=body.name)
    record_github_repo(get_upload_root(), url=info.root, name=info.name)
    return info


@router.get("", response_model=list[RepositoryInfo])
def list_repositories() -> list[RepositoryInfo]:
    return get_registry().list()


@router.get("/{repo_id}", response_model=RepositoryInfo)
def get_repository(repo_id: str) -> RepositoryInfo:
    # get_info raises RepositoryNotFoundError (HTTP 404) for an unknown id.
    return get_registry().get_info(repo_id)


@router.delete("/{repo_id}", status_code=204)
def remove_repository(repo_id: str) -> None:
    """Forget a repository from this application's in-memory registry.

    For uploaded repositories the on-disk directory is also wiped. For
    GitHub repositories nothing on the remote is touched and no MCP write
    is issued. The repo must already be registered; unknown ids 404
    (RepositoryNotFoundError).
    """

    info = get_registry().get_info(repo_id)
    get_registry().remove(repo_id)
    if info.kind is RepositoryKind.local:
        if cleanup_uploaded_repo(info.root):
            log.info(
                "removed uploaded repo directory",
                extra={"extra": {"repo_id": repo_id, "root": info.root}},
            )
    elif info.kind is RepositoryKind.github:
        if forget_github_repo(get_upload_root(), url=info.root):
            log.info(
                "removed github repo from persisted state",
                extra={"extra": {"repo_id": repo_id, "url": info.root}},
            )
