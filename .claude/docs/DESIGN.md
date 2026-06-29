# Design Document — 要件定義書 (Requirements & Macro Design)

> **Role:** Macro-level requirements and design — *what* this project builds and *why*.
> Written at `/init`, kept current by `/design-tracker` (also invoked from `/checkpointing`).
>
> **Document map:** Orchestrator contract → [CLAUDE.md](../../CLAUDE.md) ·
> Micro work progress (latest 5 checkpoints) → [PROGRESS.md](../../PROGRESS.md)

## 背景・目的 (Background & Purpose)

<!-- Why does this project exist? What problem does it solve, for whom?
     State the business/technical context and the goal in a few sentences. -->
Excel2TeX helps science and engineering students or researchers convert tabular CSV/XLSX data into LaTeX table code with a simple GUI, reducing repetitive manual `tabular` authoring work.

## スコープ (Scope)

### In Scope

<!-- What this project explicitly delivers. -->

- MVP: Load CSV/XLSX table files, generate plain LaTeX `table` and `tabular` code, preview the generated code, and copy it to the clipboard.

### Out of Scope

<!-- What is explicitly NOT covered, to prevent scope creep. -->

- MVP excludes captions, labels, alignment controls, borders, booktabs styling, and merged-cell handling.

## 機能要件 (Functional Requirements)

<!-- What the system must do. Each requirement gets a stable ID (FR-1, FR-2, ...). -->

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | Load CSV and XLSX table files. | High | CSV is the primary MVP path; XLSX is supported through pandas/openpyxl. |
| FR-2 | Convert non-empty tabular data into LaTeX `table` and `tabular` environments. | High | Default column alignment is centered for every column. |
| FR-3 | Show generated TeX in a read-only multiline preview. | High | UI responsibility only; conversion logic remains independent. |
| FR-4 | Copy generated TeX to the clipboard with user feedback. | High | Uses Flet page clipboard support. |

## 非機能要件 (Non-Functional Requirements)

<!-- Quality attributes: performance, availability, security, maintainability, etc.
     Prefer measurable targets in the Metric column. -->

| Category | Requirement | Metric / Target |
|----------|-------------|-----------------|
| Performance | Convert small report-sized tables interactively. | MVP conversion runs synchronously after file selection. |
| Availability | Run as a local Flet app. | Windows, macOS, and Linux are target platforms. |
| Security | Validate supported file extensions and avoid secrets. | Only local CSV/XLSX paths are accepted by MVP file reader. |
| Maintainability | Keep UI and conversion logic separated. | `converter.py` has no Flet dependency and is covered by pytest. |

## アーキテクチャ (Architecture)

<!-- High-level architecture: components, data flow, boundaries.
     Add a diagram or description here. -->

### Agent Roles

| Agent | Role | Responsibilities |
|-------|------|------------------|
| Codex | Implementation agent | Build Python MVP, run validation, and keep code aligned with repository rules. |

## 技術選定 (Tech Stack & Rationale)

<!-- Chosen technologies and why. Record alternatives considered. -->

| Area | Technology | Rationale | Alternatives Considered |
|------|------------|-----------|-------------------------|
| Package management | uv with `pyproject.toml` | Repository rule and reproducible dependency management. | pip/requirements.txt rejected for this project. |
| UI | Flet | Cross-platform desktop/web UI from one Python codebase. | Native GUI frameworks deferred. |
| Data loading | pandas + openpyxl | Simple CSV/XLSX ingestion and DataFrame handling. | Manual CSV parsing rejected to preserve maintainability. |
| Testing/linting | pytest + ruff | Fast unit tests and consistent Python style checks. | unittest and ad hoc formatting rejected. |

## 制約 (Constraints)

<!-- Technical, organizational, regulatory, or resource constraints. -->

- Python 3.11 or newer.
- Dependency management must use uv, not pip or requirements.txt.
- MVP must not implement captions, labels, or style controls yet.

## Key Decisions

<!-- Durable architectural/design decisions. Append-only log. -->

| Decision | Rationale | Alternatives Considered | Date |
|----------|-----------|------------------------|------|
| Implement MVP as root-level `converter.py`, `main.py`, and `tests/test_converter.py`. | Matches the MVP plan and keeps the initial project structure simple. | Package directory layout deferred until project grows. | 2026-06-29 |
| Empty DataFrames raise `ValueError` with an English, Japanese-safe message. | Prevents silently generating invalid or misleading LaTeX for files without usable table data. | Header-only output was considered but is less robust for MVP feedback. | 2026-06-29 |

## TODO / Open Questions

- [ ] 
