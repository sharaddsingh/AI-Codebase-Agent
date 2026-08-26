"use client";

import { useCallback, useEffect, useState } from "react";
import { Boxes, FolderTree } from "lucide-react";
import type { Citation, HealthResponse, RepositoryInfo } from "@/lib/types";
import { ApiError, API_BASE_URL, getHealth, listRepositories, registerRepository } from "@/lib/api";
import { RepoSelector } from "@/components/RepoSelector";
import { FileTree } from "@/components/FileTree";
import { CodeViewer, type HighlightRange } from "@/components/CodeViewer";
import { ChatPanel } from "@/components/ChatPanel";
import { EmptyState, SectionLabel } from "@/components/ui";

interface OpenFileState {
  path: string;
  highlight: HighlightRange | null;
}

export default function Page() {
  const [repos, setRepos] = useState<RepositoryInfo[]>([]);
  const [activeRepoId, setActiveRepoId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [openFile, setOpenFile] = useState<OpenFileState | null>(null);

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
      setOpenFile(null);
      void refreshHealth();
    },
    [refreshHealth],
  );

  const handleSelectRepo = useCallback((id: string) => {
    setActiveRepoId(id);
    setOpenFile(null);
  }, []);

  const handleOpenFile = useCallback((path: string) => {
    setOpenFile({ path, highlight: null });
  }, []);

  const handleOpenCitation = useCallback((c: Citation) => {
    setOpenFile({ path: c.path, highlight: { start: c.start_line, end: c.end_line } });
  }, []);

  const activeRepo = repos.find((r) => r.id === activeRepoId) ?? null;
  const modelConfigured = health?.model_configured ?? false;

  return (
    <div className="flex h-screen flex-col bg-zinc-950">
      <header className="flex flex-shrink-0 items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2.5">
        <Boxes className="h-5 w-5 text-sky-500" aria-hidden />
        <h1 className="text-sm font-semibold text-zinc-100">AI Codebase Agent</h1>
        <span className="hidden text-xs text-zinc-500 sm:inline">
          read-only investigation with file/line citations
        </span>
        {activeRepo ? (
          <span className="ml-auto truncate font-mono text-xs text-zinc-400" title={activeRepo.root}>
            {activeRepo.name}
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
                  activeFilePath={openFile?.path ?? null}
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

        {/* Center: code viewer */}
        <section className="flex min-h-[40vh] min-w-0 flex-1 flex-col border-b border-zinc-800 lg:min-h-0 lg:border-b-0">
          <CodeViewer
            repoId={activeRepoId}
            path={openFile?.path ?? null}
            highlight={openFile?.highlight ?? null}
          />
        </section>

        {/* Right: chat */}
        <aside className="flex max-h-[70vh] w-full flex-col overflow-hidden lg:max-h-none lg:w-[420px] lg:flex-shrink-0 lg:border-l lg:border-zinc-800">
          <ChatPanel
            repoId={activeRepoId}
            modelConfigured={modelConfigured}
            onOpenCitation={handleOpenCitation}
          />
        </aside>
      </main>
    </div>
  );
}
