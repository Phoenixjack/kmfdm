# AGENTS.md

## Project Purpose

KMFDM, KiCad Management of Field-Defined Metadata, is a standalone desktop application for auditing, standardizing, and bulk-editing metadata across native KiCad symbol and footprint libraries.

The tool is adjacent to the KiCad Import Assistant, but it is a separate project. The importer moves downloaded assets into controlled local libraries. KMFDM helps maintain those libraries after they exist.

## Current Design Decisions

- Use PySide6 for the GUI.
- Keep the main data grid model/view based, with `QTableView` backed by custom table models.
- Build the GUI from the start, but begin with mock data before attaching real KiCad parsers.
- Keep parser, audit, change, history, and writer logic independent from the GUI.
- Use a proper S-expression parser/tree approach for KiCad files. Do not parse KiCad library files with regular expressions.
- Regex is initially an inspection/compliance feature only. Do not implement regex replacement in the MVP.
- Enforce KiCad structural requirements, but make metadata quality policies user-defined.
- Preserve existing KiCad file content as much as practical. Avoid noisy rewrites.
- Use a KMFDM generator identifier when writing full KiCad files.
- Use a single append-only `.kmfdm-history.jsonl` sidecar log per workspace for KMFDM save history.
- Treat unknown external edits as external boundaries. Do not attribute them to KMFDM.
- Keep the app usable on Windows.
- Prefer simple, readable Python over clever abstractions.

## Non-Goals

- Do not edit symbol graphics.
- Do not edit pins.
- Do not edit footprint pad or geometry content.
- Do not edit schematic or PCB instances.
- Do not import component vendor ZIPs.
- Do not add manufacturer or distributor API lookups in the MVP.
- Do not generate BOMs.
- Do not implement AI cleanup or automatic intelligent metadata rewriting.
- Do not write legacy KiCad `.lib` or `.mod` formats.
- Do not edit KiCad database or HTTP libraries in the MVP.

## Expected Workflow

Before modifying code:

- Inspect the current repo structure.
- Summarize what files matter.
- Propose a small plan.
- Make minimal, high-confidence changes.

After modifying code:

- Run a syntax check at minimum: `python -m py_compile` against changed Python files.
- If tests exist, run them.
- Show `git diff --stat` and summarize the meaningful diff.
- Mention anything that should be manually tested in the GUI.

## File Safety

- Never print, commit, upload, or expose private local paths, customer data, downloaded vendor libraries, or user-specific KiCad paths unless the user explicitly asks.
- Do not add personal KiCad library paths to committed configuration.
- Keep generated experiments and scratch files out of committed project docs unless the user asks for them.

## First Vertical Slice

The first implementation slice should be parser-free:

1. PySide6 application shell.
2. Symbols and Footprints tabs using mock component data.
3. Cell-level state for value, issue, change source, tooltip, and save inclusion.
4. Cell inspector panel.
5. Changes tab with mock change groups and selective preview.
6. Prototype history writer/viewer using `.kmfdm-history.jsonl`.

Only after the mock-data interface behavior feels right should real KiCad parsing be connected.
