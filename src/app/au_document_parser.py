#!/usr/bin/env python3
"""
AU Document Parser — Layout-Aware Document & Table Processing Engine
Adapted from RAGFlow's Deep Document Layout Analysis (DDA) principles.

Features:
- Preserves table structures without slicing them midway.
- Converts CSV, TSV, and delimited tables into clean Markdown tables.
- Header-aware hierarchical chunking (#, ##, ###) instead of naive token slicing.
- Preserves fenced code blocks and lists intact.
"""

import os
import re
import csv
import io
from typing import List, Dict, Any, Optional

class DocumentChunk:
    def __init__(self, content: str, chunk_type: str = "text", heading: str = "", metadata: Optional[Dict[str, Any]] = None):
        self.content = content
        self.chunk_type = chunk_type  # "text", "table", "code", "list"
        self.heading = heading
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "type": self.chunk_type,
            "heading": self.heading,
            "metadata": self.metadata
        }

    def __repr__(self) -> str:
        return f"<DocumentChunk type={self.chunk_type} heading='{self.heading}' length={len(self.content)}>"

class AUDocumentParser:
    """Layout-aware document parser and chunker for local offline RAG."""

    @staticmethod
    def csv_to_markdown_table(csv_content: str, delimiter: str = ",") -> str:
        """Converts raw CSV/TSV text into a clean Markdown table."""
        try:
            reader = csv.reader(io.StringIO(csv_content.strip()), delimiter=delimiter)
            rows = list(reader)
            if not rows:
                return ""

            header = rows[0]
            if not any(header):
                return ""

            col_count = len(header)
            # Format header
            header_line = "| " + " | ".join([c.strip() for c in header]) + " |"
            sep_line = "| " + " | ".join(["---"] * col_count) + " |"

            body_lines = []
            for row in rows[1:]:
                # Pad row to match header length
                padded = row + [""] * (col_count - len(row))
                padded = padded[:col_count]
                clean_cols = [c.strip().replace("\n", " ") for c in padded]
                body_lines.append("| " + " | ".join(clean_cols) + " |")

            return "\n".join([header_line, sep_line] + body_lines)
        except Exception:
            return csv_content

    @classmethod
    def parse_file(cls, file_path: str, max_chunk_chars: int = 1500) -> List[DocumentChunk]:
        """Parses a file with layout and structure awareness."""
        path = os.path.expanduser(file_path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        ext = os.path.splitext(path)[1].lower()

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()

        if ext in (".csv", ".tsv"):
            delimiter = "\t" if ext == ".tsv" else ","
            table_md = cls.csv_to_markdown_table(raw_text, delimiter=delimiter)
            fname = os.path.basename(path)
            return [DocumentChunk(
                content=f"### Table: {fname}\n\n{table_md}",
                chunk_type="table",
                heading=fname,
                metadata={"file": path, "rows": raw_text.count("\n")}
            )]

        return cls.chunk_markdown_content(raw_text, file_name=os.path.basename(path), max_chunk_chars=max_chunk_chars)

    @classmethod
    def chunk_markdown_content(cls, text: str, file_name: str = "", max_chunk_chars: int = 1500) -> List[DocumentChunk]:
        """
        Splits Markdown or plain text into semantic chunks based on headers,
        ensuring code blocks and tables are never severed in the middle.
        """
        chunks: List[DocumentChunk] = []
        lines = text.split("\n")

        current_heading = file_name or "General"
        current_lines: List[str] = []
        in_code_block = False
        in_table_block = False

        def flush_chunk(ctype: str = "text"):
            nonlocal current_lines
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append(DocumentChunk(
                    content=content,
                    chunk_type=ctype,
                    heading=current_heading,
                    metadata={"file": file_name, "char_count": len(content)}
                ))
            current_lines = []

        for line in lines:
            trimmed = line.strip()

            # Track fenced code block state
            if trimmed.startswith("```"):
                if in_code_block:
                    current_lines.append(line)
                    in_code_block = False
                    flush_chunk("code")
                    continue
                else:
                    if current_lines and len("\n".join(current_lines)) > 200:
                        flush_chunk("text")
                    in_code_block = True
                    current_lines.append(line)
                    continue

            if in_code_block:
                current_lines.append(line)
                continue

            # Track table blocks
            is_table_line = trimmed.startswith("|") and trimmed.endswith("|")
            if is_table_line:
                if not in_table_block:
                    if current_lines:
                        flush_chunk("text")
                    in_table_block = True
                current_lines.append(line)
                continue
            elif in_table_block:
                in_table_block = False
                flush_chunk("table")

            # Check header lines
            header_match = re.match(r'^(#{1,4})\s+(.+)$', line)
            if header_match:
                if current_lines:
                    flush_chunk("text")
                current_heading = header_match.group(2).strip()
                current_lines.append(line)
                continue

            current_lines.append(line)

            # Split if chunk exceeds character target on a natural paragraph boundary
            current_length = sum(len(l) for l in current_lines)
            if current_length >= max_chunk_chars and (not trimmed or trimmed.endswith(".")):
                flush_chunk("text")

        # Flush any remaining buffer
        if current_lines:
            flush_chunk("code" if in_code_block else ("table" if in_table_block else "text"))

        return chunks

if __name__ == "__main__":
    sample_doc = """# MacBook M4 Architecture Overview

The Apple Silicon M4 features a 10-core CPU and 10-core GPU with 16GB Unified Memory.

## Memory Specifications

| Component | Bandwidth | Capacity | Architecture |
| Unified RAM | 120 GB/s | 16 GB | Shared LPDDR5X |
| System Cache | High | 16 MB | Shared L2/SLC |

## Code Implementation
```python
def check_m4():
    return "M4 Metal Accelerated"
```

## Next Steps
Continue developing offline AI tools with local-first persistence.
"""
    parser = AUDocumentParser()
    chunks = parser.chunk_markdown_content(sample_doc, file_name="m4_specs.md")
    print(f"Generated {len(chunks)} layout-aware chunks:")
    for i, c in enumerate(chunks):
        print(f"\n--- Chunk {i+1} [{c.chunk_type}] (Heading: {c.heading}) ---")
        print(c.content)
