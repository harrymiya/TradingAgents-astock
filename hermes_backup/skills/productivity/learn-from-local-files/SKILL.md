---
name: learn-from-local-files
description: Systematically read, decode, and absorb knowledge from a user's local file repository across multiple file formats, building expertise in a domain.
category: productivity
tags: [file-reading, knowledge-acquisition, document-decoding, research]
---

# Learn from Local Files

A structured approach for reading and absorbing knowledge from a user's personal file repository. Use when the user says "go look at my files about X" or "here's a folder of materials, learn this topic."

## Trigger Conditions

- User says "go look at my files about [topic]" or "there should be materials about X on disk"
- User asks you to become an expert in a topic and points to local files
- User shares that they have a curated collection of documents on a subject
- User wants you to learn from their personal knowledge base

## Workflow

### Phase 1: Discover the repository

1. **Discover the files** — use `search_files` with topic-relevant keywords (Chinese and English) to locate the data:
   - `search_files(pattern="keyword", target="files", path="~/")` to find by filename
   - `terminal("find ... -type d | sort")` to see directory structure (Chinese-language directories may not show in search_files)
   - Check common content directories: `下载/`, `文档/`, `桌面/`, `Documents/`, `Desktop/`, `Downloads/`

2. **Map the structure** — use `terminal("find ... -type d | sort")` to get a complete directory tree. This reveals the organizational logic (numbered folders, categories, sub-topics).

3. **Identify small files first** — sort by size to find documents you can read quickly:
   ```bash
   find /path -type f \( -name "*.txt" -o -name "*.doc" -o -name "*.pdf" \) -exec ls -lh {} \; 2>/dev/null | awk '{print $5, $NF}' | sort -h | head -20
   ```
   Start with the smallest files (<50K). They tend to be the most condensed/精华 content.

### Phase 2: Decode and read

4. **Handle encoding** — Chinese text files often use GBK/GB2312/GB18030 encoding:
   - Try `chardet` first: `python3 -c "import chardet; print(chardet.detect(raw))"`
   - Fallback: try gbk, gb2312, gb18030 in order
   - Use `python3 << 'PYEOF' ... with open(f, 'r', encoding='gbk') ... PYEOF` (heredoc avoids shell escaping issues)

5. **Handle legacy .doc format** — Old Word `.doc` (Composite Document File V2) requires conversion:
   ```bash
   libreoffice --headless --convert-to txt:"Text" "file.doc" --outdir /tmp/outdir
   ```
   - Pre-install: `sudo apt-get install -y libreoffice` if not available
   - `python-docx` does NOT support old .doc format (throws PackageNotFoundError)
   - `antiword` and `catdoc` are alternatives but libreoffice is more reliable

6. **Handle .docx** — Use python-docx:
   ```python
   from docx import Document
   doc = Document('file.docx')
   text = '\n'.join([p.text for p in doc.paragraphs])
   ```

7. **Handle .pdf** — Use `pdftotext` (poppler-utils) or `marker-pdf`:
   ```bash
   pdftotext file.pdf -  # to stdout
   ```

8. **Read phase** — For each document:
   - Read the full content with `terminal()` + python heredoc
   - For long files, read in sections with `offset`/`limit` via `read_file`

### Phase 3: Digest and store

9. **Immediately store learned knowledge** — after each document or batch:
   - `memory(action='replace'/'add', target='memory')` with structured summary
   - Group related documents together in one memory entry
   - Include: source filename, key concepts, core claims, practical techniques, limitations/caveats

10. **Layer learning** — read in order of dependency:
    - Start with overview/summary documents (心法荟萃, 奥义)
    - Then supporting technique docs (MACD, 连线)
    - Then detailed references and raw source material

### Pitfalls

- **Chinese encoding**: `read_file` tool may not auto-detect GBK. Always check encoding with `file` or `chardet` first. Use python heredoc with explicit encoding.
- **Legacy .doc fails python-docx**: Old `.doc` (pre-2007) is not the same as `.docx`. LibreOffice headless conversion is the reliable path.
- **search_files with Chinese queries**: searching by Chinese character filename may return 0 results due to encoding issues in the tool. Use `find` via `terminal()` as fallback for directory listing.
- **Truncated results**: Large directories (>100 files) may be truncated. Use `offset` parameter or `find` with more specific globs.
- **Results truncated in search_files**: Use `offset=` for pagination when a directory has many files.
- **Memory space**: Memory entries have limited character space (~2200 chars). For comprehensive topic knowledge, use `replace` to merge related entries rather than adding separate ones.
- **Don't rely on file extensions**: Many `.doc` files are actually HTML or RTF in disguise. Check with `file` command first.
- **baiduyun partial downloads**: Skip files with `baiduyun.p.downloading` suffix — they're incomplete.
