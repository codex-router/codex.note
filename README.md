# codex.note

AI-assisted code note generator for **C**, **C++**, **Java**, **Go**, **Python**, **Bash**, **JavaScript/TypeScript**, and **Rust** projects.

This module provides a practical two-pass pipeline:

1. **Analysis pass**: summarize each module from source chunks into structured JSON.
2. **Note pass**: generate Markdown note pages from those summaries.

It is model-agnostic and works with OpenAI-compatible chat-completions endpoints.

---

## Features

- Scans supported source files recursively (C/C++, Java, Go, Python, Bash, JavaScript/TypeScript, Rust)
- Splits large repositories into prompt-friendly chunks
- Generates one note page per top-level module plus a system overview
- Generates calling graphs using Mermaid diagrams
- Stores intermediate analysis artifacts for traceability
- Supports `--dry-run` to preview plan without model calls

---

## Requirements

- Python 3.9+
- OpenAI-compatible endpoint and API key

---

## Quick Start

### 1) Configure environment variables

```bash
export LITELLM_BASE_URL="https://litellm.com/v1"
export LITELLM_API_KEY="<your-api-key>"
export LITELLM_MODEL="ollama-gemini-3-flash-preview"
```

`LITELLM_BASE_URL` accepts either:

- a full API root ending in `/v1` (for example `https://litellm.com/v1`)
- or a gateway root like `https://your-gateway/openai` (the tool auto-appends `/v1/chat/completions`)

### 2) Run generator

```bash
python generate_note.py --repo /path/to/project --out ./note
```

This writes:

- `note/System-Architecture.md`
- `note/<module>.md` pages
- `.codex-note/analysis/*.json` intermediate files

---

## Usage

```text
python generate_note.py \
	--repo <path-to-project> \
	--out <path-to-note-output> \
	[--max-files-per-module 40] \
	[--max-chars-per-file 10000] \
	[--include "src/**"] \
	[--exclude "**/build/**"] \
	[--dry-run]
```

### Common examples

Generate note for a Java/Maven project:

```bash
python generate_note.py --repo /path/to/project --out ./note
```

Generate note for a Go/Python/JS/Rust monorepo:

```bash
python generate_note.py --repo /path/to/repo --out ./note
```

Generate note while limiting scope:

```bash
python generate_note.py \
	--repo /path/to/project \
	--out ./note \
	--include "src/**" \
	--exclude "**/third_party/**"
```

Preview modules and chunking only:

```bash
python generate_note.py --repo /path/to/project --out ./note --dry-run
```

---

## Docker

Build image:

```bash
docker build -t craftslab/codex-note:latest .
```

Run container:

```bash
docker run --rm \
	-e LITELLM_BASE_URL="${LITELLM_BASE_URL:-https://litellm.com/v1}" \
	-e LITELLM_API_KEY="$LITELLM_API_KEY" \
	-e LITELLM_MODEL="${LITELLM_MODEL:-ollama-gemini-3-flash-preview}" \
	-v "/path/to/workspace:/workspace" \
	craftslab/codex-note:latest \
	--repo /workspace/project \
	--out /workspace/note
```

---

## Prompt Templates

Templates are plain text files under `prompts/`:

- `prompts/analysis_prompt.txt`
- `prompts/note_prompt.txt`

You can edit these templates to tune output style or enforce internal standards.

---

## Output Structure

```text
codex.note/
	generate_note.py
	prompts/
		analysis_prompt.txt
		note_prompt.txt
	note/
		System-Architecture.md
		<module>.md
	.codex-note/
		analysis/
			<module>.json
```

---

## Notes

- The tool only uses provided source snippets; when uncertain, pages mark items as `TBD`.
- For very large repos, run incrementally by pointing `--include` to specific subtrees.

---

## License

Licensed under the Apache License, Version 2.0.

