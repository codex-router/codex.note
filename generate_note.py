#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib import error, request


SOURCE_EXTENSIONS = {
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hh",
    ".hxx",
    ".java",
    ".go",
    ".py",
    ".pyi",
    ".sh",
    ".bash",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".rs",
}


@dataclass
class FileSnippet:
    path: str
    content: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate code note from C/C++/Java/Go/Python/Bash/JavaScript/TypeScript/Rust repos using AI prompts.",
    )
    parser.add_argument("--repo", required=True, help="Path to target source repository")
    parser.add_argument("--out", required=True, help="Path to generated note directory")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Glob include filter relative to repo (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=["**/.git/**", "**/target/**", "**/build/**", "**/node_modules/**"],
        help="Glob exclude filter relative to repo (repeatable)",
    )
    parser.add_argument(
        "--max-files-per-module",
        type=int,
        default=40,
        help="Max file snippets per module",
    )
    parser.add_argument(
        "--max-chars-per-file",
        type=int,
        default=10000,
        help="Maximum chars loaded from each source file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print discovered modules/files and exit",
    )
    return parser.parse_args()


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_prompt_template(template_name: str) -> str:
    here = Path(__file__).resolve().parent
    template_path = here / "prompts" / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Missing prompt template: {template_path}")
    return load_text(template_path).strip()


def should_include(rel_path: str, includes: list[str], excludes: list[str]) -> bool:
    normalized = rel_path.replace("\\", "/")
    if includes:
        matched_include = any(fnmatch.fnmatch(normalized, pattern) for pattern in includes)
        if not matched_include:
            return False
    if any(fnmatch.fnmatch(normalized, pattern) for pattern in excludes):
        return False
    return True


def discover_source_files(repo: Path, includes: list[str], excludes: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        rel = path.relative_to(repo).as_posix()
        if should_include(rel, includes, excludes):
            files.append(path)
    files.sort()
    return files


def choose_module(rel_path: str) -> str:
    parts = rel_path.split("/")
    for anchor in ("src", "include", "lib", "app"):
        if anchor in parts:
            idx = parts.index(anchor)
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return parts[0] if parts else "root"


def load_snippets(
    repo: Path,
    source_files: Iterable[Path],
    max_chars_per_file: int,
    max_files_per_module: int,
) -> dict[str, list[FileSnippet]]:
    modules: dict[str, list[FileSnippet]] = {}
    for file_path in source_files:
        rel = file_path.relative_to(repo).as_posix()
        module = choose_module(rel)
        module_files = modules.setdefault(module, [])
        if len(module_files) >= max_files_per_module:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = text[:max_chars_per_file]
        module_files.append(FileSnippet(path=rel, content=text))
    return modules


def resolve_chat_completions_url(api_base: str) -> str:
    normalized = api_base.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def make_chat_request(messages: list[dict[str, str]]) -> str:
    api_base = os.getenv("LITELLM_BASE_URL", "https://litellm.com/v1").rstrip("/")
    api_key = os.getenv("LITELLM_API_KEY")
    model = os.getenv("LITELLM_MODEL", "ollama-gemini-3-flash-preview")

    if not api_key:
        raise RuntimeError("LITELLM_API_KEY is required")

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": messages,
    }
    data = json.dumps(payload).encode("utf-8")
    request_url = resolve_chat_completions_url(api_base)

    req = request.Request(
        url=request_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "codex-note/1.0",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise RuntimeError(
                "AI request failed: "
                f"{exc.code} {detail}. "
                f"url={request_url}. "
                "Check LITELLM_BASE_URL and LITELLM_API_KEY; for OpenAI-compatible gateways, "
                "use a base URL like https://host/v1 or https://host/openai."
            ) from exc
        raise RuntimeError(f"AI request failed: {exc.code} {detail}. url={request_url}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"AI request failed: {exc}") from exc

    parsed = json.loads(body)
    return parsed["choices"][0]["message"]["content"]


def build_analysis_payload(module: str, snippets: list[FileSnippet]) -> str:
    items = []
    for index, snippet in enumerate(snippets, 1):
        items.append(
            {
                "snippet_id": f"{module}-{index}",
                "path": snippet.path,
                "content": snippet.content,
            }
        )
    return json.dumps({"module": module, "snippets": items}, ensure_ascii=False)


def save_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def sanitize_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    return safe.strip("-") or "module"


def generate_module_analysis(module: str, snippets: list[FileSnippet], analysis_prompt: str) -> dict:
    user_payload = build_analysis_payload(module, snippets)
    content = make_chat_request(
        [
            {"role": "system", "content": analysis_prompt},
            {"role": "user", "content": user_payload},
        ]
    )
    content = content.strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end >= start:
        content = content[start:end+1]
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def generate_module_note(module: str, analysis_json: dict, note_prompt: str) -> str:
    user_payload = json.dumps({"module": module, "analysis": analysis_json}, ensure_ascii=False)
    return make_chat_request(
        [
            {"role": "system", "content": note_prompt},
            {"role": "user", "content": user_payload},
        ]
    )


def build_system_page(module_pages: list[str]) -> str:
    lines = ["# System Architecture", "", "## Module Pages", ""]
    for page in module_pages:
        title = Path(page).stem
        lines.append(f"- [{title}]({page})")
    lines.append("")
    lines.append("## Generation Notes")
    lines.append("")
    lines.append("- Generated by `generate_note.py` in two-pass mode (analysis -> note).")
    lines.append("- Unknown or uncertain details are intentionally marked as `TBD`.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    state_dir = Path(__file__).resolve().parent / ".codex-note" / "analysis"

    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Repo path not found: {repo}")

    source_files = discover_source_files(repo, args.include, args.exclude)
    modules = load_snippets(
        repo=repo,
        source_files=source_files,
        max_chars_per_file=args.max_chars_per_file,
        max_files_per_module=args.max_files_per_module,
    )

    if not modules:
        raise SystemExit(
            "No matching source files were found for supported languages: C/C++, Java, Go, Python, Bash, JavaScript, TypeScript, Rust."
        )

    print(f"Discovered {len(source_files)} source files in {len(modules)} modules")
    for module, snippets in sorted(modules.items()):
        print(f"  - {module}: {len(snippets)} snippets")

    if args.dry_run:
        print("Dry run enabled; no AI calls were made.")
        return 0

    analysis_prompt = read_prompt_template("analysis_prompt.txt")
    note_prompt = read_prompt_template("note_prompt.txt")

    out.mkdir(parents=True, exist_ok=True)
    module_pages: list[str] = []

    for module, snippets in sorted(modules.items()):
        print(f"[1/2] Analyzing module: {module}")
        analysis = generate_module_analysis(module, snippets, analysis_prompt)
        analysis_path = state_dir / f"{sanitize_filename(module)}.json"
        save_json(analysis_path, analysis)

        print(f"[2/2] Generating note page: {module}")
        markdown = generate_module_note(module, analysis, note_prompt)
        page_name = f"{sanitize_filename(module)}.md"
        (out / page_name).write_text(markdown.strip() + "\n", encoding="utf-8")
        module_pages.append(page_name)

    system_page = build_system_page(sorted(module_pages))
    (out / "System-Architecture.md").write_text(system_page, encoding="utf-8")
    print(f"Done. note written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
