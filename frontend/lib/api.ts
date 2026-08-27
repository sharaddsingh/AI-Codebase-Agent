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

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
    res = await fetch(`${API_BASE_URL}/api${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
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

export function registerRepository(
  path: string,
  name?: string,
  signal?: AbortSignal,
): Promise<RepositoryInfo> {
  return request<RepositoryInfo>("/repositories", {
    method: "POST",
    body: JSON.stringify({ path, ...(name ? { name } : {}) }),
    signal,
  });
}

/**
 * Unregister a repository from the app's in-memory registry (backend
 * `DELETE /repositories/{id}`, 204 → no body). This only makes the app *forget*
 * the repository — it never deletes local files, the local directory, or the
 * GitHub repository, and issues no git/MCP write. Distinct from closing an
 * editor tab, which is a pure client-side UI action.
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
