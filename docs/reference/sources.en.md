# Source file formats

> 🌐 **English** | [한국어](sources.md)

## Source file formats

`/factlog sync` extracts facts by reading each file under `sources/` **as text,
in-session**. The bundled engine (`merge_candidates.py`) tracks every file as a
source *path* but never parses contents — so a file is only ingested if its text
can be read during extraction. A binary original (e.g. `.docx`) therefore yields
no facts on its own.

| Format | Status | Notes |
|--------|--------|-------|
| `.md`, `.markdown`, `.txt` | **Directly supported** | UTF-8 text, read verbatim. This is what every extraction reference assumes. |
| Other UTF-8 text (`.rst`, `.org`, `.csv`, source code) | Supported as plain text | No special parsing; treated as raw text. |
| `.docx`, binary `.pdf`, `.odt`, `.epub`, `.html`, `.rtf` | **Auto-converted** | `factlog ingest` converts these to text via pandoc / textutil / pdftotext. |
| `.hwpx` (Hancom OWPML) | **Auto-converted** | Built-in extractor (no external tool) — reads the zip's `Contents/section*.xml` text. |
| `.hwp` (legacy Hancom, HWP 5.x) | **Auto-converted** | Via `hwp5html` (pyhwp) → pandoc → markdown, tables preserved. Needs `pip install pyhwp` + pandoc; if absent, reported with a hint. |
| `.pptx` (PowerPoint) | **Auto-converted** | Built-in extractor (no external tool) — reads on-slide text from the zip's `ppt/slides/slideN.xml`, slides in order, one block per slide. Speaker notes are excluded; table cells flatten to one line per cell (row/column grouping not preserved). |
| `.xlsx`, images | **Not converted** | No bundled converter — reported with a hint; convert by hand. |

`factlog ingest` writes the converted text into the KB's **`runs/sources/`**
directory (alongside the other generated run artifacts) — **never into
`sources/`**, which stays the user's originals. A conversion is named by the
original's **full filename (extension included) + the converter's suffix**
(`report.hwpx` → `runs/sources/report.hwpx.md`, `report.pptx` →
`runs/sources/report.pptx.md`), so two originals in one folder that share a stem
and differ only in extension never **collide on one conversion and lose the
loser**. A nested original mirrors its subdirectory
(`sources/sub/report.pdf` → `runs/sources/sub/report.pdf.md`), so same-name
files in different folders never collide either. The original is left
untouched and the conversion carries a provenance header (source, converter,
date). Both `sources/` and `runs/sources/` are valid source roots that
extraction reads.

> **Upgrading (#213):** the conversion filename rule changed. It used to use the
> original's **stem** only (`report.pdf` → `runs/sources/report.md`); it now uses
> the original's **full name** (`runs/sources/report.pdf.md`), so `report.hwpx`
> and `report.pptx` in one folder are each preserved as their own conversion.
> A legacy stem-named conversion (`runs/sources/report.md`) in an already-ingested
> KB is **still paired with its original through a stem-based fallback** by
> `factlog sources` / `coverage` / `status`, so it is not silently lost. To move
> to the new layout, re-run `factlog ingest --scan --force` (then clean up any
> leftover legacy conversions with `factlog eject --orphans`). A KB whose stems
> collided in particular must be re-ingested to restore the originals that were
> being lost.

> **Upgrading:** subdirectory mirroring is newer than the original flat layout.
> A KB ingested earlier has flat conversions (`runs/sources/report.md`) for
> nested originals; those no longer pair, so a nested binary may reappear as a
> coverage/`factlog sources` gap. Re-run `factlog ingest --scan --force` to move
> conversions to their mirrored paths (then delete any stale flat conversions).
> Top-level (non-nested) sources are unaffected.

```bash
factlog ingest report.docx --target ~/wiki   # → ~/wiki/runs/sources/report.docx.md (pandoc)
factlog ingest --scan --target ~/wiki        # auto-convert every binary under sources/
```

`/factlog sync` runs `factlog ingest --scan` as its first step, so binaries you
drop in `sources/` are converted automatically (idempotently — unchanged files
are skipped). If a binary has no `runs/sources/` conversion, `merge_candidates.py`
warns so the silent non-ingestion is visible.
