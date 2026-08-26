"use client";

import { useState } from "react";
import { FolderGit2, Github, Plus, ShieldAlert } from "lucide-react";
import type { HealthResponse, RepositoryInfo, RepositoryKind } from "@/lib/types";
import { ApiError } from "@/lib/api";
import { Badge, ErrorBanner, SectionLabel, Spinner } from "./ui";

const SAMPLE_PATH = "tests/fixtures/sample_repo";
// A tiny, canonical public repo for demoing GitHub registration.
const SAMPLE_GITHUB_URL = "https://github.com/octocat/Hello-World";

function KindBadge({ kind }: { kind: RepositoryKind }) {
  return kind === "github" ? (
    <Badge tone="blue" title="Read over the GitHub API (read-only)">
      GitHub
    </Badge>
  ) : (
    <Badge tone="neutral" title="Read from the local filesystem">
      Local
    </Badge>
  );
}

interface RepoSelectorProps {
  repos: RepositoryInfo[];
  activeRepoId: string | null;
  health: HealthResponse | null;
  healthError: string | null;
  onSelectRepo: (id: string) => void;
  onRegister: (path: string, name?: string) => Promise<void>;
}

export function RepoSelector({
  repos,
  activeRepoId,
  health,
  healthError,
  onSelectRepo,
  onRegister,
}: RepoSelectorProps) {
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeRepo = repos.find((r) => r.id === activeRepoId) ?? null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = path.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onRegister(trimmed);
      setPath("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to register repository.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <HealthIndicator health={health} healthError={healthError} />

      <form onSubmit={submit} className="flex flex-col gap-2">
        <SectionLabel>Register a repository</SectionLabel>
        <div className="flex gap-2">
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="Local path or GitHub URL (https://github.com/owner/repo)"
            spellCheck={false}
            disabled={busy}
            className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 focus:border-sky-600 focus:outline-none disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || path.trim() === ""}
            className="inline-flex items-center gap-1 rounded-md bg-sky-700 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? <Spinner className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
            Register
          </button>
        </div>
        {repos.length === 0 ? (
          <div className="flex flex-col gap-1 text-[11px] text-zinc-500">
            <p>
              {"No repositories yet. Try the bundled local sample: "}
              <button
                type="button"
                onClick={() => setPath(SAMPLE_PATH)}
                className="font-mono text-sky-400 underline decoration-dotted hover:text-sky-300"
              >
                {SAMPLE_PATH}
              </button>
            </p>
            <p>
              {"…or a public GitHub repo: "}
              <button
                type="button"
                onClick={() => setPath(SAMPLE_GITHUB_URL)}
                className="font-mono text-sky-400 underline decoration-dotted hover:text-sky-300"
              >
                {SAMPLE_GITHUB_URL}
              </button>
            </p>
          </div>
        ) : null}
        {error ? <ErrorBanner title="Registration failed" message={error} onDismiss={() => setError(null)} /> : null}
      </form>

      {repos.length > 0 ? (
        <div className="flex flex-col gap-2">
          <SectionLabel>Repositories ({repos.length})</SectionLabel>
          <div className="flex flex-col gap-1">
            {repos.map((repo) => {
              const isActive = repo.id === activeRepoId;
              const Icon = repo.kind === "github" ? Github : FolderGit2;
              return (
                <button
                  key={repo.id}
                  type="button"
                  onClick={() => onSelectRepo(repo.id)}
                  className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs transition-colors ${
                    isActive
                      ? "border-sky-700 bg-sky-950/50 text-zinc-100"
                      : "border-zinc-800 bg-zinc-900/40 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
                  <span className="min-w-0 flex-1 truncate font-medium">{repo.name}</span>
                  <span
                    className={`flex-shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide ${
                      repo.kind === "github"
                        ? "bg-sky-950 text-sky-300"
                        : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {repo.kind}
                  </span>
                  {repo.file_count_hint != null ? (
                    <span className="flex-shrink-0 text-[10px] text-zinc-500">
                      {repo.file_count_hint} files
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {activeRepo ? <ActiveRepoDetails repo={activeRepo} /> : null}
    </div>
  );
}

function ActiveRepoDetails({ repo }: { repo: RepositoryInfo }) {
  const isGithub = repo.kind === "github";
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-2.5 text-xs">
      {isGithub ? (
        <a
          href={repo.root}
          target="_blank"
          rel="noreferrer noopener"
          className="mb-1 block truncate font-mono text-[11px] text-sky-400 underline decoration-dotted hover:text-sky-300"
          title={repo.root}
        >
          {repo.root}
        </a>
      ) : (
        <div className="mb-1 truncate font-mono text-[11px] text-zinc-400" title={repo.root}>
          {repo.root}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        <KindBadge kind={repo.kind} />
        <Badge tone="violet" title="Snapshot id">
          {repo.snapshot.id}
        </Badge>
        {repo.snapshot.dirty ? <Badge tone="amber">dirty</Badge> : null}
        {repo.file_count_hint != null ? (
          <Badge tone="neutral">{repo.file_count_hint} files</Badge>
        ) : null}
      </div>
    </div>
  );
}

function HealthIndicator({
  health,
  healthError,
}: {
  health: HealthResponse | null;
  healthError: string | null;
}) {
  if (healthError) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-red-900 bg-red-950/50 px-2.5 py-1.5 text-xs text-red-300">
        <span className="h-2 w-2 flex-shrink-0 rounded-full bg-red-500" />
        <span className="truncate">{healthError}</span>
      </div>
    );
  }
  if (!health) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900/40 px-2.5 py-1.5 text-xs text-zinc-400">
        <Spinner className="h-3 w-3" />
        Checking backend…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-zinc-800 bg-zinc-900/40 px-2.5 py-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-medium text-zinc-300">
          <span
            className={`h-2 w-2 rounded-full ${
              health.model_configured ? "bg-emerald-500" : "bg-red-500"
            }`}
          />
          Backend online
        </span>
        <Badge tone={health.model_configured ? "green" : "red"}>
          {health.model_configured ? "model ready" : "model not set"}
        </Badge>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
        <span className="font-mono">
          {health.model_provider} · {health.model}
        </span>
      </div>
      {health.unrestricted_roots ? (
        <Badge tone="amber" title="ALLOWED_REPO_ROOTS is empty on the backend — any path can be registered.">
          <ShieldAlert className="h-3 w-3" /> unrestricted roots
        </Badge>
      ) : null}
    </div>
  );
}
