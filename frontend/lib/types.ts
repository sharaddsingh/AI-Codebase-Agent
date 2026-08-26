// Types mirror the backend API contract exactly. Kept free of any runtime
// dependency so they can be imported from both server and client code and from
// pure unit tests.

export type RepositoryKind = "local" | "github";
export type FileType = "file" | "dir" | "symlink" | "other";

export interface RepoSnapshot {
  id: string;
  kind: string;
  revision: string | null;
  dirty: boolean;
  captured_at: string;
}

export interface RepositoryInfo {
  id: string;
  name: string;
  kind: RepositoryKind;
  root: string;
  snapshot: RepoSnapshot;
  registered_at: string;
  file_count_hint: number | null;
}

export interface FileEntry {
  path: string;
  name: string;
  type: FileType;
  size: number | null;
}

export interface DirectoryListing {
  repo_id: string;
  path: string;
  entries: FileEntry[];
  total: number;
  page: number;
  page_size: number;
  truncated: boolean;
}

export interface FileContent {
  repo_id: string;
  path: string;
  start_line: number;
  end_line: number;
  total_lines: number;
  content: string;
  truncated: boolean;
  encoding: string;
  bytes_returned: number;
}

export interface FileMetadata {
  repo_id: string;
  path: string;
  size_bytes: number;
  line_count: number | null;
  language: string | null;
  is_binary: boolean;
  modified_at: string;
  sha256: string;
}

export interface SearchMatch {
  path: string;
  line_number: number;
  line: string;
  context: string | null;
}

export interface SearchResults {
  repo_id: string;
  query: string;
  matches: SearchMatch[];
  total_matches: number;
  truncated: boolean;
  engine: string;
  // Coverage caveat when the search did not scan the whole repository (e.g. a
  // bounded GitHub search). Absent/null when the search was exhaustive.
  notes?: string | null;
}

export interface Citation {
  path: string;
  start_line: number;
  end_line: number;
  snapshot_id: string | null;
}

export interface HealthResponse {
  status: string;
  model_provider: string;
  model_configured: boolean;
  model: string;
  repositories: number;
  unrestricted_roots: boolean;
}

// ---- Agent streaming (SSE) ----

export type AgentEventType =
  | "status"
  | "classified"
  | "plan"
  | "tool_call"
  | "tool_result"
  | "token"
  | "answer"
  | "error"
  | "budget"
  | "done";

export interface AgentEvent {
  type: AgentEventType;
  message: string | null;
  data: Record<string, any> | null;
  step: number | null;
}

export interface AgentResult {
  answer: string;
  citations: Citation[];
  task_type: string;
  steps: number;
  tool_calls: number;
  files_read: string[];
  stop_reason: string;
  budget_exhausted: boolean;
  snapshot_id: string | null;
  usage: Record<string, any> | null;
}

// ---- Request bodies ----

export interface RegisterRepoRequest {
  path: string;
  name?: string;
}

export interface AgentChatRequest {
  repo_id: string;
  question: string;
}

// ---- Error envelope ----

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
