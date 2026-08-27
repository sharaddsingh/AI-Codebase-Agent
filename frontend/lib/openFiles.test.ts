import { describe, expect, it } from "vitest";
import {
  EMPTY_OPEN_FILES,
  MAX_OPEN_FILES,
  activeFile,
  closeFile,
  openFile,
  setActive,
  type OpenFilesState,
} from "./openFiles";
import * as api from "./api";

/** Paths in tab (display) order — the strip the user actually sees. */
const paths = (s: OpenFilesState): string[] => s.files.map((f) => f.path);

describe("openFile — from the file tree", () => {
  it("opens a file and makes it active", () => {
    const s = openFile(EMPTY_OPEN_FILES, "a.ts");
    expect(paths(s)).toEqual(["a.ts"]);
    expect(s.activePath).toBe("a.ts");
    expect(activeFile(s)?.highlight).toBeNull();
  });

  it("does not duplicate an already-open file; re-activates it in place", () => {
    let s = openFile(EMPTY_OPEN_FILES, "a.ts");
    s = openFile(s, "b.ts");
    s = openFile(s, "a.ts"); // re-open a from the tree
    expect(paths(s)).toEqual(["a.ts", "b.ts"]); // stable order, no dup
    expect(s.activePath).toBe("a.ts");
  });

  it("appends new tabs to the end and keeps their order", () => {
    let s = openFile(EMPTY_OPEN_FILES, "a.ts");
    s = openFile(s, "b.ts");
    s = openFile(s, "c.ts");
    expect(paths(s)).toEqual(["a.ts", "b.ts", "c.ts"]);
    expect(s.activePath).toBe("c.ts");
  });
});

describe("openFile — from a citation", () => {
  it("opens the cited file, activates it, and carries the highlight range", () => {
    const s = openFile(EMPTY_OPEN_FILES, "src/x.ts", { start: 5, end: 63 });
    expect(s.activePath).toBe("src/x.ts");
    expect(activeFile(s)?.highlight).toEqual({ start: 5, end: 63 });
  });

  it("re-activates and updates the highlight when the cited file is already open", () => {
    let s = openFile(EMPTY_OPEN_FILES, "src/x.ts");
    s = openFile(s, "y.ts");
    s = openFile(s, "src/x.ts", { start: 20, end: 25 }); // citation into open x
    expect(paths(s)).toEqual(["src/x.ts", "y.ts"]); // no duplicate
    expect(s.activePath).toBe("src/x.ts");
    expect(activeFile(s)?.highlight).toEqual({ start: 20, end: 25 });
  });
});

describe("setActive — switching tabs", () => {
  it("switches the active tab without reordering the strip", () => {
    let s = openFile(EMPTY_OPEN_FILES, "a.ts");
    s = openFile(s, "b.ts");
    s = openFile(s, "c.ts");
    s = setActive(s, "a.ts");
    expect(paths(s)).toEqual(["a.ts", "b.ts", "c.ts"]);
    expect(s.activePath).toBe("a.ts");
  });

  it("is a no-op for a path that is not open", () => {
    const s = openFile(EMPTY_OPEN_FILES, "a.ts");
    expect(setActive(s, "ghost.ts")).toBe(s);
  });
});

describe("closeFile", () => {
  it("removes only the closed tab and preserves the others", () => {
    let s = openFile(EMPTY_OPEN_FILES, "a.ts");
    s = openFile(s, "b.ts");
    s = openFile(s, "c.ts"); // active c
    s = closeFile(s, "b.ts"); // close an inactive middle tab
    expect(paths(s)).toEqual(["a.ts", "c.ts"]);
    expect(s.activePath).toBe("c.ts"); // active unchanged
  });

  it("closing the active tab focuses the previously opened neighbor (open A, open B, close B -> A active)", () => {
    let s = openFile(EMPTY_OPEN_FILES, "A.ts");
    s = openFile(s, "B.ts"); // active B
    s = closeFile(s, "B.ts");
    expect(paths(s)).toEqual(["A.ts"]);
    expect(s.activePath).toBe("A.ts");
  });

  it("shows the empty state (null active) when the last tab is closed", () => {
    let s = openFile(EMPTY_OPEN_FILES, "only.ts");
    s = closeFile(s, "only.ts");
    expect(paths(s)).toEqual([]);
    expect(s.activePath).toBeNull();
    expect(activeFile(s)).toBeNull();
  });

  it("is a no-op when closing a file that isn't open", () => {
    const s = openFile(EMPTY_OPEN_FILES, "a.ts");
    expect(closeFile(s, "ghost.ts")).toBe(s);
  });

  it("does not mutate the input state (pure transform)", () => {
    const before = openFile(openFile(EMPTY_OPEN_FILES, "a.ts"), "b.ts");
    const snapshot = JSON.stringify(before);
    const after = closeFile(before, "a.ts");
    expect(JSON.stringify(before)).toBe(snapshot); // input untouched
    expect(after).not.toBe(before);
  });
});

describe("MAX_OPEN_FILES eviction", () => {
  it("evicts the oldest inactive tab when opening beyond the cap", () => {
    let s = EMPTY_OPEN_FILES;
    for (let i = 1; i <= MAX_OPEN_FILES; i++) s = openFile(s, `f${i}.ts`);
    expect(s.files).toHaveLength(MAX_OPEN_FILES);

    s = openFile(s, "new.ts"); // one past the cap
    expect(s.files).toHaveLength(MAX_OPEN_FILES); // capped
    expect(paths(s)).not.toContain("f1.ts"); // oldest inactive removed
    expect(paths(s)).toContain("new.ts");
    expect(s.activePath).toBe("new.ts");
  });

  it("never evicts the active tab, even when it is the least recently used", () => {
    let s = EMPTY_OPEN_FILES;
    for (let i = 1; i <= MAX_OPEN_FILES; i++) s = openFile(s, `f${i}.ts`);
    s = setActive(s, "f1.ts"); // the oldest-opened tab is now the active one

    s = openFile(s, "new.ts");
    expect(s.files).toHaveLength(MAX_OPEN_FILES);
    expect(paths(s)).toContain("f1.ts"); // active protected from eviction
    expect(paths(s)).not.toContain("f2.ts"); // next-least-recently-used evicted instead
  });
});

describe("repository safety — a tab close never deletes a repo file", () => {
  it("exposes no file-content mutation in the API client (only the two intentional registry mutations)", () => {
    // The guarantee is structural. Exactly two client functions mutate anything,
    // and both touch only the in-memory *registry*: registerRepository (add a
    // repo to the app's list) and removeRepository (forget one from it).
    // "Remove repository" is NOT "delete files": the backend DELETE only drops
    // the registry entry — no filesystem, git, or GitHub write. Every other
    // export is a read. So, setting that allow-list aside, no client function
    // may look like a content mutation — which is why closing a tab (pure UI
    // state) cannot possibly mutate, delete, or write a repository or its files.
    const intentionalRegistryMutations = ["registerRepository", "removeRepository"];
    const forbidden = /delete|remove|unregister|destroy|\bwrite\b|\bput\b|\bpatch\b/i;
    const offenders = Object.entries(api)
      .filter(([, value]) => typeof value === "function")
      .map(([name]) => name)
      .filter((name) => !intentionalRegistryMutations.includes(name))
      .filter((name) => forbidden.test(name));
    expect(offenders).toEqual([]);
  });

  it("closing a tab changes only the open-files list and active pointer", () => {
    let s = openFile(EMPTY_OPEN_FILES, "keep.ts");
    s = openFile(s, "close-me.ts");
    const after = closeFile(s, "close-me.ts");
    expect(paths(after)).toEqual(["keep.ts"]);
    // No field that could represent a repository mutation exists on the state.
    expect(Object.keys(after).sort()).toEqual(["activePath", "files", "mru"]);
  });
});
