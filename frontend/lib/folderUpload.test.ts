import { describe, expect, it } from "vitest";
import {
  collectDropEntries,
  flattenFileList,
  walkDropEntries,
  walkHandle,
  type FileSystemDirectoryEntryLike,
  type FileSystemDirectoryHandleLike,
  type FileSystemEntryLike,
} from "./folderUpload";

// ---- fakes ----------------------------------------------------------------
// Minimal stand-ins for the three browser APIs. They implement only the shape
// the walkers touch, including `readEntries`' pagination — which is the whole
// point of one of the tests below.

function file(name: string, body = "x"): File {
  return new File([body], name, { type: "text/plain" });
}

/** A `webkitGetAsEntry()` file entry. */
function fileEntry(name: string): FileSystemEntryLike {
  return {
    isFile: true,
    isDirectory: false,
    name,
    fullPath: `/${name}`,
    file: (cb: (f: File) => void) => cb(file(name)),
  } as FileSystemEntryLike;
}

/**
 * A `webkitGetAsEntry()` directory entry whose reader pages `children` out in
 * batches of `batchSize`, exactly like Chrome's 100-entry pagination.
 */
function dirEntry(
  name: string,
  children: FileSystemEntryLike[],
  batchSize = 100,
): FileSystemDirectoryEntryLike {
  return {
    isFile: false,
    isDirectory: true,
    name,
    fullPath: `/${name}`,
    createReader: () => {
      let cursor = 0;
      return {
        readEntries: (cb: (entries: FileSystemEntryLike[]) => void) => {
          const batch = children.slice(cursor, cursor + batchSize);
          cursor += batch.length;
          // Async, like the real callback API.
          setTimeout(() => cb(batch), 0);
        },
      };
    },
  };
}

/** A `showDirectoryPicker()` directory handle. */
function dirHandle(
  name: string,
  children: Array<FileSystemDirectoryHandleLike | { kind: "file"; name: string }>,
): FileSystemDirectoryHandleLike {
  return {
    name,
    values: () =>
      (async function* () {
        for (const c of children) {
          if ("values" in c) yield { ...c, kind: "directory" as const };
          else yield { kind: "file" as const, name: c.name, getFile: async () => file(c.name) };
        }
      })(),
  } as FileSystemDirectoryHandleLike;
}

function fileListOf(paths: string[]): ArrayLike<File> {
  return paths.map((p) => {
    const f = file(p.split("/").pop() ?? p);
    Object.defineProperty(f, "webkitRelativePath", { value: p });
    return f;
  });
}

const paths = (r: { files: { relativePath: string }[] }) =>
  r.files.map((f) => f.relativePath);

// ---- showDirectoryPicker --------------------------------------------------

describe("walkHandle", () => {
  it("yields paths relative to the picked folder, not including its name", async () => {
    const out: { relativePath: string; file: File }[] = [];
    await walkHandle(
      dirHandle("my-project", [
        { kind: "file", name: "README.md" },
        dirHandle("app", [{ kind: "file", name: "main.py" }]),
      ]),
      "",
      out,
    );
    expect(out.map((f) => f.relativePath).sort()).toEqual(["README.md", "app/main.py"]);
  });
});

// ---- drag and drop --------------------------------------------------------

describe("walkDropEntries", () => {
  it("strips the dropped folder's own name and returns it as the display name", async () => {
    // Regression: the walk used to prefix every path with the dropped folder's
    // name, so the tree arrived one level deeper than showDirectoryPicker's.
    const result = await walkDropEntries([
      dirEntry("my-project", [
        fileEntry("README.md"),
        dirEntry("app", [fileEntry("main.py")]),
      ]),
    ]);
    expect(paths(result).sort()).toEqual(["README.md", "app/main.py"]);
    expect(result.name).toBe("my-project");
  });

  it("reads every page of a directory, not just the first batch", async () => {
    // Regression: `readEntries` was called once. Chrome caps each call at 100
    // entries, so anything past the first page vanished with no error.
    const children = Array.from({ length: 250 }, (_, i) => fileEntry(`f${i}.txt`));
    const result = await walkDropEntries([dirEntry("big", children, 100)]);
    expect(result.files).toHaveLength(250);
    expect(paths(result)).toContain("f249.txt");
  });

  it("pages nested directories too", async () => {
    const nested = Array.from({ length: 120 }, (_, i) => fileEntry(`n${i}.txt`));
    const result = await walkDropEntries([
      dirEntry("root", [dirEntry("deep", nested, 100)]),
    ]);
    expect(result.files).toHaveLength(120);
    expect(paths(result)).toContain("deep/n119.txt");
  });

  it("keeps each item's own name when several are dropped at once", async () => {
    // No single root exists, so nothing is stripped and the server names the repo.
    const result = await walkDropEntries([
      dirEntry("a", [fileEntry("x.txt")]),
      dirEntry("b", [fileEntry("y.txt")]),
    ]);
    expect(paths(result).sort()).toEqual(["a/x.txt", "b/y.txt"]);
    expect(result.name).toBeUndefined();
  });

  it("handles a single dropped file", async () => {
    const result = await walkDropEntries([fileEntry("notes.md")]);
    expect(paths(result)).toEqual(["notes.md"]);
    expect(result.name).toBeUndefined();
  });
});

describe("collectDropEntries", () => {
  it("collects every item's entry, skipping items that expose none", () => {
    const entry = fileEntry("a.txt");
    const items = [
      { webkitGetAsEntry: () => entry },
      { webkitGetAsEntry: () => null },
      { webkitGetAsEntry: () => entry },
    ] as unknown as DataTransferItemList;
    expect(collectDropEntries(items)).toHaveLength(2);
  });

  it("tolerates a null item list", () => {
    expect(collectDropEntries(null)).toEqual([]);
  });
});

// ---- <input webkitdirectory> ----------------------------------------------

describe("flattenFileList", () => {
  it("strips the shared root segment and returns it as the display name", () => {
    const result = flattenFileList(
      fileListOf(["my-project/README.md", "my-project/app/main.py"]),
    );
    expect(paths(result)).toEqual(["README.md", "app/main.py"]);
    expect(result.name).toBe("my-project");
  });

  it("leaves paths alone when they do not share one root", () => {
    const result = flattenFileList(fileListOf(["a/x.txt", "b/y.txt"]));
    expect(paths(result)).toEqual(["a/x.txt", "b/y.txt"]);
    expect(result.name).toBeUndefined();
  });

  it("leaves a flat multi-file selection alone", () => {
    const result = flattenFileList(fileListOf(["x.txt", "y.txt"]));
    expect(paths(result)).toEqual(["x.txt", "y.txt"]);
    expect(result.name).toBeUndefined();
  });

  it("normalizes backslashes before comparing roots", () => {
    const result = flattenFileList(
      fileListOf(["my-project\\app\\main.py", "my-project\\README.md"]),
    );
    expect(paths(result)).toEqual(["app/main.py", "README.md"]);
    expect(result.name).toBe("my-project");
  });

  it("returns nothing for an empty list", () => {
    expect(flattenFileList([])).toEqual({ files: [], name: undefined });
  });
});
