"use client";

import { useCallback, useEffect, useState } from "react";
import { Boxes, FolderGit2, FolderTree, Github } from "lucide-react";
import type { Citation, HealthResponse, RepositoryInfo } from "@/lib/types";
import { ApiError, API_BASE_URL, getHealth, listRepositories, registerRepository, removeRepository } from "@/lib/api";
import {
  EMPTY_OPEN_FILES,
  activeFile,
  closeFile,
  openFile,
  setActive,
  type HighlightRange,
} from "@/lib/openFiles";
import { RepoSelector } from "@/components/RepoSelector";
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
  // Open editor tabs (a UI-only list, distinct from the repository's files).
  const [openFiles, setOpenFiles] = useState(EMPTY_OPEN_FILES);
  // The repo awaiting removal confirmation (drives the ConfirmDialog).
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

  // Initial load: health + repositories.
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

  const handleRegister = useCallback(
    async (path: string, name?: string) => {
      const repo = await registerRepository(path, name);
      setRepos((prev) => [...prev.filter((r) => r.id !== repo.id), repo]);
      setActiveRepoId(repo.id);
      setOpenFiles(EMPTY_OPEN_FILES); // tabs are per-repo; start fresh
      void refreshHealth();
    },
    [refreshHealth],
  );

  const handleSelectRepo = useCallback((id: string) => {
    setActiveRepoId(id);
    setOpenFiles(EMPTY_OPEN_FILES); // switching repos clears the open tabs
  }, []);

  // Remove repository — a two-step, confirmed flow. Step 1: open the dialog.
  const handleRequestRemove = useCallback((repo: RepositoryInfo) => {
    setRemovalError(null);
    setPendingRemoval(repo);
  }, []);

  // Step 2: confirmed. Ask the backend to *forget* the repo (never deletes any
  // file or the GitHub repository), then reconcile local UI state.
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
        // The active repo was removed: fall back to the next one (or none) and
        // clear the editor tabs/viewer, which belonged to the removed repo.
        // Clearing activeRepoId also clears the FileTree (keyed by it).
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
    if (removalBusy) return; // don't dismiss mid-request
    setPendingRemoval(null);
    setRemovalError(null);
  }, [removalBusy]);

  // File tree click → open (or re-activate) the file, no highlight.
  const handleOpenFile = useCallback((path: string) => {
    setOpenFiles((s) => openFile(s, path));
  }, []);

  // Citation click → open (or re-activate) and navigate to the cited range.
  const handleOpenCitation = useCallback((c: Citation) => {
    const highlight: HighlightRange = { start: c.start_line, end: c.end_line };
    setOpenFiles((s) => openFile(s, c.path, highlight));
  }, []);

  // Tab strip interactions.
  const handleSelectTab = useCallback((path: string) => {
    setOpenFiles((s) => setActive(s, path));
  }, []);
  const handleCloseTab = useCallback((path: string) => {
    setOpenFiles((s) => closeFile(s, path));
  }, []);

  const activeRepo = repos.find((r) => r.id === activeRepoId) ?? null;
  const modelConfigured = health?.model_configured ?? false;
  const active = activeFile(openFiles);

  return (
    <div className="flex h-screen flex-col bg-zinc-950">
      <header className="flex flex-shrink-0 items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2.5">
        <Boxes className="h-5 w-5 flex-shrink-0 text-sky-500" aria-hidden />
        <h1 className="flex-shrink-0 text-sm font-semibold text-zinc-100">AI Codebase Agent</h1>
        <span className="hidden flex-shrink-0 text-xs text-zinc-500 sm:inline">
          read-only investigation with file/line citations
        </span>
        {activeRepo ? (
          <span
            className="ml-auto flex min-w-0 items-center gap-1.5 pl-2 text-xs text-zinc-400"
            title={`${activeRepo.name} · ${activeRepo.root}`}
          >
            {activeRepo.kind === "github" ? (
              <Github className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
            ) : (
              <FolderGit2 className="h-3.5 w-3.5 flex-shrink-0 text-zinc-500" aria-hidden />
            )}
            <span className="min-w-0 truncate font-mono">{activeRepo.name}</span>
          </span>
        ) : null}
      </header>

      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Left: repo selector + file tree */}
        <aside className="flex max-h-[45vh] w-full flex-col overflow-hidden border-b border-zinc-800 lg:max-h-none lg:w-80 lg:flex-shrink-0 lg:border-b-0 lg:border-r">
          <div className="flex-shrink-0 overflow-y-auto p-3">
            <RepoSelector
              repos={repos}
              activeRepoId={activeRepoId}
              health={health}
              healthError={healthError}
              onSelectRepo={handleSelectRepo}
              onRegister={handleRegister}
              onRemove={handleRequestRemove}
            />
          </div>
          <div className="flex min-h-0 flex-1 flex-col border-t border-zinc-800">
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
                  Register a repository above to browse its files.
                </EmptyState>
              )}
            </div>
          </div>
        </aside>

        {/* Center: open-files tabs + code viewer */}
        <section className="flex min-h-[40vh] min-w-0 flex-1 flex-col border-b border-zinc-800 lg:min-h-0 lg:border-b-0">
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
        </section>

        {/* Right: chat */}
        <aside className="flex max-h-[70vh] w-full flex-col overflow-hidden lg:max-h-none lg:w-[420px] lg:flex-shrink-0 lg:border-l lg:border-zinc-800">
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
