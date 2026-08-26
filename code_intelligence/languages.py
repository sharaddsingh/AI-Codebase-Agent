"""Language detection and binary sniffing by file extension / content."""

from __future__ import annotations

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".jsonc": "json",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-cpp",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".env": "dotenv",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
    ".vue": "vue",
    ".svelte": "svelte",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".xml": "xml",
}

# Extensions we treat as binary without reading content.
_BINARY_EXTS: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
        ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".war",
        ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib", ".class", ".pyc", ".pyo",
        ".wasm", ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
        ".mp3", ".mp4", ".mov", ".avi", ".wav", ".flac", ".ogg", ".webm",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".pack", ".idx", ".node",
    }
)


def guess_language(filename: str) -> str | None:
    """Return a language slug for a filename, or None if unknown."""

    lower = filename.lower()
    # A few well-known extensionless / special filenames.
    base = lower.rsplit("/", 1)[-1]
    if base in ("dockerfile",):
        return "dockerfile"
    if base in ("makefile", "gnumakefile"):
        return "makefile"
    dot = lower.rfind(".")
    if dot == -1:
        return None
    return _EXT_TO_LANG.get(lower[dot:])


def is_binary_ext(filename: str) -> bool:
    lower = filename.lower()
    dot = lower.rfind(".")
    return dot != -1 and lower[dot:] in _BINARY_EXTS


def looks_binary(sample: bytes) -> bool:
    """Heuristic: content with a NUL byte in its first chunk is treated as binary."""

    return b"\x00" in sample
