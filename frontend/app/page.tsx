"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FolderTree } from "lucide-react";
import type { Citation, HealthResponse, RepositoryInfo } from "@/lib/types";
import {
  ApiError,
  API_BASE_URL,
  getHealth,
  listRepositories,
  registerGitHubRepository,
  removeRepository,
  uploadRepository,
  type UploadFileLike,
} from "@/lib/api";
import {
  EMPTY_OPEN_FILES,
  activeFile,
  closeFile,
  openFile,
  setActive,
  type HighlightRange,
} from "@/lib/openFiles";
import { Header } from "@/components/Header";
import { RepoPanel } from "@/components/RepoPanel";
import { FileTree } from "@/components/FileTree";
import { CodeViewer } from "@/components/CodeViewer";
import { OpenFilesBar } from "@/components/OpenFilesBar";
import { ChatPanel } from "@/components/ChatPanel";
import { ConfirmDialog, EmptyState, SectionLabel } from "@/components/ui";

export default function Page() {
  const [repos, setRepos] = useState<RepositoryInfo[]>([]);
  const [activeRepoId, setActiveRepoId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [openFiles, setOpenFiles] = useState(EMPTY_OPEN_FILES);
  const [pendingRemoval, setPendingRemoval] = useState<RepositoryInfo | null>(null);
  const [removalBusy, setRemovalBusy] = useState(false);
  const [removalError, setRemovalError] = useState<string | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await getHealth();
      setHealth(h);
      setHealthError(null);
    } catch (err) {
      setHealth(null);
      setHealthError(
        err instanceof ApiError
          ? err.message
          : `Cannot reach the backend at ${API_BASE_URL}.`,
      );
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    listRepositories()
      .then((list) => {
        setRepos(list);
        setActiveRepoId((cur) => cur ?? (list.length > 0 ? list[0].id : null));
      })
      .catch(() => {
        // health error already surfaces the connectivity problem
      });
  }, [refreshHealth]);

  const handleUploaded = useCallback(
    async (files: UploadFileLike[], name?: string) => {
      const repo = await uploadRepository(files, name);
      setRepos((prev) => [...prev.filter((r) => r.id !== repo.id), repo]);
      setActiveRepoId(repo.id);
      setOpenFiles(EMPTY_OPEN_FILES);
      void refreshHealth();
    },
    [refreshHealth],
  );

  const handleRegisterGitHub = useCallback(
    async (url: string, name?: string) => {
      const repo = await registerGitHubRepository(url, name);
      setRepos((prev) => [...prev.filter((r) => r.id !== repo.id), repo]);
      setActiveRepoId(repo.id);
      setOpenFiles(EMPTY_OPEN_FILES);
      void refreshHealth();
    },
    [refreshHealth],
  );

  const handleSelectRepo = useCallback((id: string) => {
    setActiveRepoId(id);
    setOpenFiles(EMPTY_OPEN_FILES);
  }, []);

  const handleRequestRemove = useCallback((repo: RepositoryInfo) => {
    setRemovalError(null);
    setPendingRemoval(repo);
  }, []);

  const confirmRemoval = useCallback(async () => {
    const repo = pendingRemoval;
    if (!repo) return;
    setRemovalBusy(true);
    setRemovalError(null);
    try {
      await removeRepository(repo.id);
      const remaining = repos.filter((r) => r.id !== repo.id);
      setRepos(remaining);
      if (activeRepoId === repo.id) {
        setActiveRepoId(remaining.length > 0 ? remaining[0].id : null);
        setOpenFiles(EMPTY_OPEN_FILES);
      }
      setPendingRemoval(null);
    } catch (err) {
      setRemovalError(err instanceof ApiError ? err.message : "Failed to remove repository.");
    } finally {
      setRemovalBusy(false);
    }
  }, [pendingRemoval, repos, activeRepoId]);

  const cancelRemoval = useCallback(() => {
    if (removalBusy) return;
    setPendingRemoval(null);
  }, [removalBusy]);

  const handleOpenCitation = useCallback((citation: Citation) => {
    setOpenFiles((s) =>
      openFile(s, citation.path, {
        start: citation.start_line,
        end: citation.end_line,
      }),
    );
  }, []);

  const handleOpenFile = useCallback((path: string) => {
    setOpenFiles((s) => openFile(s, path));
  }, []);

  const handleSelectTab = useCallback((path: string) => {
    setOpenFiles((s) => setActive(s, path));
  }, []);
  const handleCloseTab = useCallback((path: string) => {
    setOpenFiles((s) => closeFile(s, path));
  }, []);

  const activeRepo = useMemo(
    () => repos.find((r) => r.id === activeRepoId) ?? null,
    [repos, activeRepoId],
  );
  const modelConfigured = health?.model_configured ?? false;
  const active = activeFile(openFiles);
  const hasRepos = repos.length > 0;

  return (
    <div className="relative flex h-screen flex-col">
      <Header health={health} healthError={healthError} />

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Left rail: RepoPanel is ALWAYS visible so the Upload + GitHub
            tiles are always reachable, even on the empty state. */}
        <aside className="flex max-h-[45vh] w-full flex-col overflow-hidden border-b border-slate-line lg:max-h-none lg:w-[320px] lg:flex-shrink-0 lg:border-b-0 lg:border-r">
          <div className="flex-shrink-0 overflow-y-auto p-3">
            <RepoPanel
              repos={repos}
              activeRepoId={activeRepoId}
              health={health}
              healthError={healthError}
              onSelectRepo={handleSelectRepo}
              onUpload={handleUploaded}
              onRegisterGitHub={handleRegisterGitHub}
              onRemove={handleRequestRemove}
            />
          </div>
          {hasRepos ? (
            <div className="flex min-h-0 flex-1 flex-col border-t border-slate-line">
              <div className="flex-shrink-0 px-3 pt-2">
                <SectionLabel>Files</SectionLabel>
              </div>
              <div className="min-h-0 flex-1 overflow-auto px-1 pb-2">
                {activeRepoId ? (
                  <FileTree
                    key={activeRepoId}
                    repoId={activeRepoId}
                    activeFilePath={active?.path ?? null}
                    onOpenFile={handleOpenFile}
                  />
                ) : (
                  <EmptyState
                    title="No repository selected"
                    icon={<FolderTree className="h-7 w-7" />}
                  >
                    Pick a repository above to browse its files.
                  </EmptyState>
                )}
              </div>
            </div>
          ) : null}
        </aside>

        {/* Center: empty-state hero when no repos, otherwise the open-files
            strip + code viewer. */}
        <section className="flex min-h-[40vh] min-w-0 flex-1 flex-col border-b border-slate-line lg:min-h-0 lg:border-b-0">
          {hasRepos ? (
            <>
              <OpenFilesBar
                files={openFiles.files}
                activePath={openFiles.activePath}
                onSelect={handleSelectTab}
                onClose={handleCloseTab}
              />
              <div className="min-h-0 flex-1">
                <CodeViewer
                  repoId={activeRepoId}
                  path={active?.path ?? null}
                  highlight={active?.highlight ?? null}
                />
              </div>
            </>
          ) : (
            <EmptyReposHero />
          )}
        </section>

        {/* Right rail: chat. Always present; the panel itself disables input
            until a repository is selected. */}
        <aside className="flex max-h-[70vh] w-full flex-col overflow-hidden border-t border-slate-line lg:max-h-none lg:w-[420px] lg:flex-shrink-0 lg:border-l lg:border-t-0">
          <ChatPanel
            key={activeRepoId ?? "none"}
            repoId={activeRepoId}
            modelConfigured={modelConfigured}
            onOpenCitation={handleOpenCitation}
          />
        </aside>
      </main>

      <ConfirmDialog
        open={pendingRemoval !== null}
        title="Remove repository?"
        message="Remove this repository from the AI Codebase Agent?"
        detail="This does not delete the repository or any files."
        error={removalError}
        confirmLabel="Remove"
        tone="danger"
        busy={removalBusy}
        onConfirm={confirmRemoval}
        onCancel={cancelRemoval}
      />
    </div>
  );
}

// ---- Empty state: full-bleed rotating 3D plane with folder + GitHub mark --

function EmptyReposHero() {
  return (
    <div className="relative flex h-full w-full items-center justify-center px-6">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div
          className="absolute left-1/2 top-1/3 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-50 blur-3xl"
          style={{
            background:
              "radial-gradient(circle, rgba(124,92,255,0.45) 0%, rgba(34,211,238,0.25) 45%, transparent 70%)",
          }}
        />
      </div>

      <div className="relative flex max-w-md flex-col items-center gap-5 text-center animate-fade-in">
        <div
          className="relative h-44 w-44"
          style={{ perspective: "800px" }}
          aria-hidden
        >
          <div
            className="absolute inset-0 animate-plane-spin rounded-3xl"
            style={{
              background:
                "conic-gradient(from 0deg, rgba(124,92,255,0.0), rgba(124,92,255,0.6), rgba(34,211,238,0.5), rgba(124,92,255,0.0))",
              transformOrigin: "50% 50%",
              maskImage:
                "linear-gradient(135deg, black, transparent 60%), radial-gradient(circle at 50% 50%, black 60%, transparent 70%)",
              WebkitMaskImage:
                "linear-gradient(135deg, black, transparent 60%), radial-gradient(circle at 50% 50%, black 60%, transparent 70%)",
              opacity: 0.6,
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center gap-4">
            <FolderMark />
            <GithubMark />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-shimmer text-2xl font-bold tracking-tight">
            Bring your codebase.
          </h2>
          <p className="text-sm text-zinc-400">
            Drop a folder, or paste a GitHub URL — pick one of the tiles on the
            left to get started.
            <br />
            <span className="text-zinc-500">
              The agent investigates read-only and cites every line.
            </span>
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 text-[11px] text-zinc-500">
          <Pill tone="cyan">Drop folder</Pill>
          <Pill tone="violet">github.com/owner/repo</Pill>
          <Pill tone="neutral">No filesystem access on the server</Pill>
        </div>
      </div>
    </div>
  );
}

function Pill({ children, tone }: { children: React.ReactNode; tone: "cyan" | "violet" | "neutral" }) {
  const cls =
    tone === "cyan"
      ? "border-cyan-brand/40 bg-cyan-brand/10 text-cyan-brand-soft"
      : tone === "violet"
      ? "border-violet-brand/40 bg-violet-brand/10 text-violet-brand-soft"
      : "border-slate-line bg-slate-panel/60 text-zinc-400";
  return (
    <span
      className={
        "inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono " +
        cls
      }
    >
      {children}
    </span>
  );
}

function FolderMark() {
  return (
    <svg
      viewBox="0 0 64 64"
      className="h-14 w-14 drop-shadow-[0_8px_24px_rgba(34,211,238,0.35)]"
      aria-hidden
    >
      <defs>
        <linearGradient id="folder-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <path
        d="M8 20 Q8 16 12 16 H24 L28 20 H52 Q56 20 56 24 V46 Q56 50 52 50 H12 Q8 50 8 46 Z"
        fill="url(#folder-grad)"
        opacity="0.9"
      />
      <path
        d="M8 26 H56 V46 Q56 50 52 50 H12 Q8 50 8 46 Z"
        fill="rgba(34,211,238,0.55)"
      />
      <path
        d="M16 34 H48 M16 40 H40"
        stroke="rgba(10,10,15,0.6)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function GithubMark() {
  return (
    <svg
      viewBox="0 0 64 64"
      className="h-14 w-14 drop-shadow-[0_8px_24px_rgba(124,92,255,0.35)]"
      aria-hidden
    >
      <defs>
        <linearGradient id="gh-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#9b87ff" />
          <stop offset="100%" stopColor="#7c5cff" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="26" fill="url(#gh-grad)" />
      <path
        d="M32 18 C24 18 18 24 18 32 C18 38 22 43 27 45 V42 C23 43 22 41 22 41 C20 38 22 38 22 38 C22 38 23 36 25 36 C25 36 28 36 30 38 C32 39 35 38 35 37 C34 35 33 33 33 31 C30 30 28 28 28 25 C28 23 29 22 30 21 C30 20 30 19 30 18 C32 18 34 19 35 19 C36 19 38 18 40 18 C40 19 40 20 40 21 C41 22 42 23 42 25 C42 28 40 30 37 31 C37 33 36 35 35 37 C37 38 39 39 42 38 C42 38 44 38 42 41 C42 41 41 43 37 42 V45 C42 43 46 38 46 32 C46 24 40 18 32 18 Z"
        fill="rgba(10,10,15,0.85)"
      />
    </svg>
  );
}