// Typed fetch client for the backend. Every non-2xx response carries the
// backend error envelope `{ error: { code, message } }`; we unwrap it into an
// `ApiError` so callers can surface `error.message` directly. A failed fetch
// (backend down / CORS) becomes an `ApiError` with a helpful, human message.

import type {
  DirectoryListing,
  FileContent,
  FileMetadata,
  HealthResponse,
  RepositoryInfo,
  SearchResults,
} from "./types";

// `NEXT_PUBLIC_API_BASE_URL` may be given either as an origin
// ("http://localhost:8000", the local-dev default) or as a same-origin path
// prefix ("/api" or "" — what the single-image Docker/Render/Fly deploy uses,
// where one process serves both the API and the static frontend).
//
// `API_ROOT` normalizes both into a base that already contains exactly one
// "/api" segment, so callers append only the endpoint path. Without this,
// setting the env var to "/api" produced requests to "/api/api/health".
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export const API_ROOT = /(^|\/)api$/.test(API_BASE_URL)
  ? API_BASE_URL
  : `${API_BASE_URL}/api`;

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** True when the failure was reaching the server at all (vs. an HTTP error). */
export function isNetworkError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 0;
}

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    usp.set(key, String(value));
  }
  const q = usp.toString();
  return q ? `?${q}` : "";
}

async function extractError(res: Response): Promise<ApiError> {
  let message = res.statusText || `Request failed (${res.status})`;
  let code = "http_error";
  try {
    const body: unknown = await res.json();
    if (
      body &&
      typeof body === "object" &&
      "error" in body &&
      body.error &&
      typeof body.error === "object"
    ) {
      const envelope = (body as { error: { code?: string; message?: string } }).error;
      if (typeof envelope.message === "string") message = envelope.message;
      if (typeof envelope.code === "string") code = envelope.code;
    }
  } catch {
    // non-JSON error body; keep the status-derived message
  }
  return new ApiError(message, code, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `Could not reach the backend at ${API_BASE_URL}. Is it running?`,
      "network_error",
      0,
    );
  }

  if (!res.ok) {
    throw await extractError(res);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// ---- Endpoints ----

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { signal });
}

export function listRepositories(signal?: AbortSignal): Promise<RepositoryInfo[]> {
  return request<RepositoryInfo[]>("/repositories", { signal });
}

export function getRepository(repoId: string, signal?: AbortSignal): Promise<RepositoryInfo> {
  return request<RepositoryInfo>(`/repositories/${encodeURIComponent(repoId)}`, { signal });
}

/**
 * Register a GitHub repository by URL. The backend talks to the official GitHub
 * MCP server and returns the standard :class:`RepositoryInfo`. A malformed URL
 * throws :class:`ApiError` with code ``invalid_github_url``.
 */
export function registerGitHubRepository(
  url: string,
  name?: string,
  signal?: AbortSignal,
): Promise<RepositoryInfo> {
  return request<RepositoryInfo>("/repositories/github", {
    method: "POST",
    body: JSON.stringify({ url, ...(name ? { name } : {}) }),
    signal,
  });
}

export interface UploadProgress {
  totalBytes: number;
  sentBytes: number;
  filesTotal: number;
  filesAdded: number;
}

export interface UploadFileLike {
  /** Repo-relative path, using forward slashes. */
  relativePath: string;
  file: File;
}

/**
 * Upload a browser-picked folder to ``POST /api/repositories/upload``.
 *
 * Streams the files as a multipart form. ``name`` is the picked folder's own
 * name, sent as a form field so the repo shows up under that name instead of
 * its content-hash directory. ``onProgress`` is called with the running totals
 * so the UI can show a progress bar. The endpoint enforces containment,
 * ignore-dir, and size caps; an exceeded cap or other validation failure
 * surfaces as an :class:`ApiError`.
 */
export function uploadRepository(
  files: UploadFileLike[],
  name: string | undefined,
  options?: { onProgress?: (p: UploadProgress) => void; signal?: AbortSignal },
): Promise<RepositoryInfo> {
  const form = new FormData();
  // Send the name first so the server has it before the file parts stream in.
  if (name) form.append("name", name);
  for (const f of files) {
    // The backend reads each part's ``filename`` as the repo-relative path.
    form.append("files", f.file, f.relativePath);
  }
  return xhrUpload(form, options);
}

function xhrUpload(
  form: FormData,
  options?: { onProgress?: (p: UploadProgress) => void; signal?: AbortSignal },
): Promise<RepositoryInfo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_ROOT}/repositories/upload`);
    xhr.responseType = "json";

    const filesTotal = form.getAll("files").length;
    let filesAdded = 0;

    xhr.upload.addEventListener("progress", (e) => {
      if (!options?.onProgress || !e.lengthComputable) return;
      options.onProgress({
        totalBytes: e.total,
        sentBytes: e.loaded,
        filesTotal,
        filesAdded,
      });
    });
    // XHR doesn't fire per-file progress, so we approximate filesAdded by
    // counting how many file parts we appended (the browser flushes them in
    // submission order). Best-effort — the bar moves primarily with bytes.
    let lastTotal = 0;
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) lastTotal = e.total;
    });
    xhr.upload.addEventListener("load", () => {
      filesAdded = filesTotal;
      options?.onProgress?.({
        totalBytes: lastTotal,
        sentBytes: lastTotal,
        filesTotal,
        filesAdded,
      });
    });

    xhr.addEventListener("load", () => {
      const status = xhr.status;
      if (status >= 200 && status < 300) {
        resolve(xhr.response as RepositoryInfo);
        return;
      }
      let message = xhr.statusText || `Upload failed (${status})`;
      let code = "http_error";
      const body = xhr.response as { error?: { code?: string; message?: string } } | null;
      if (body?.error) {
        if (typeof body.error.message === "string") message = body.error.message;
        if (typeof body.error.code === "string") code = body.error.code;
      }
      reject(new ApiError(message, code, status));
    });
    xhr.addEventListener("error", () => {
      reject(
        new ApiError(
          `Could not reach the backend at ${API_BASE_URL}. Is it running?`,
          "network_error",
          0,
        ),
      );
    });
    xhr.addEventListener("abort", () => {
      reject(new ApiError("Upload aborted.", "aborted", 0));
    });

    options?.signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(form);
  });
}

/**
 * Unregister a repository from the app's in-memory registry (backend
 * `DELETE /repositories/{id}`, 204 → no body). This only makes the app *forget*
 * the repository — for uploaded repos the on-disk directory is also wiped, but
 * for GitHub repos nothing on the remote is touched and no MCP write is
 * issued. Distinct from closing an editor tab, which is a pure client-side UI
 * action.
 */
export function removeRepository(repoId: string, signal?: AbortSignal): Promise<void> {
  return request<void>(`/repositories/${encodeURIComponent(repoId)}`, {
    method: "DELETE",
    signal,
  });
}

export function getTree(
  repoId: string,
  path: string,
  opts?: { page?: number; pageSize?: number; signal?: AbortSignal },
): Promise<DirectoryListing> {
  const query = buildQuery({ path, page: opts?.page, page_size: opts?.pageSize });
  return request<DirectoryListing>(
    `/repositories/${encodeURIComponent(repoId)}/tree${query}`,
    { signal: opts?.signal },
  );
}

export function getFile(
  repoId: string,
  path: string,
  opts?: {
    startLine?: number;
    endLine?: number;
    maxBytes?: number;
    signal?: AbortSignal;
  },
): Promise<FileContent> {
  const query = buildQuery({
    path,
    start_line: opts?.startLine,
    end_line: opts?.endLine,
    max_bytes: opts?.maxBytes,
  });
  return request<FileContent>(
    `/repositories/${encodeURIComponent(repoId)}/file${query}`,
    { signal: opts?.signal },
  );
}

export function getMetadata(
  repoId: string,
  path: string,
  signal?: AbortSignal,
): Promise<FileMetadata> {
  const query = buildQuery({ path });
  return request<FileMetadata>(
    `/repositories/${encodeURIComponent(repoId)}/metadata${query}`,
    { signal },
  );
}

export function searchCode(
  repoId: string,
  query: string,
  opts?: {
    regex?: boolean;
    caseSensitive?: boolean;
    pathGlob?: string;
    maxResults?: number;
    signal?: AbortSignal;
  },
): Promise<SearchResults> {
  const qs = buildQuery({
    query,
    regex: opts?.regex,
    case_sensitive: opts?.caseSensitive,
    path_glob: opts?.pathGlob,
    max_results: opts?.maxResults,
  });
  return request<SearchResults>(
    `/repositories/${encodeURIComponent(repoId)}/search${qs}`,
    { signal: opts?.signal },
  );
}
