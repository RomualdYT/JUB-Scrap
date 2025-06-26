"""Index and search UPC decision PDFs.

This script extracts text from PDF files listed in the Excel sheet
produced by ``scrap_html.py``. It builds a Whoosh index containing the
PDF text and basic metadata (date, registry number, parties, etc.). The
command line interface provides two actions:

* ``index`` - populate/update the search index
* ``search`` - query the index by keyword and optional date range

Example usage:

    python index_pdfs.py index --excel decisions_html.xlsx
    python index_pdfs.py search --query injunction --start 2023-01-01

"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from pdfminer.high_level import extract_text
from whoosh import index
from whoosh.fields import DATETIME, ID, TEXT, Schema
from whoosh.qparser import MultifieldParser
from whoosh.query import DateRange

DEFAULT_EXCEL = Path("decisions_html.xlsx")
DEFAULT_INDEX_DIR = Path("indexdir")


def build_schema() -> Schema:
    return Schema(
        path=ID(stored=True, unique=True),
        date=DATETIME(stored=True),
        registry=TEXT(stored=True),
        parties=TEXT(stored=True),
        court=TEXT(stored=True),
        action=TEXT(stored=True),
        content=TEXT,
    )


def create_or_open_index(index_dir: Path) -> index.Index:
    if index.exists_in(index_dir):
        return index.open_dir(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    return index.create_in(index_dir, build_schema())


def parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except Exception:
        return None


def do_index(args: argparse.Namespace) -> None:
    excel_path = Path(args.excel)
    if not excel_path.is_file():
        raise SystemExit(f"Excel file not found: {excel_path}")

    ix = create_or_open_index(Path(args.index_dir))
    # Read the Excel data as strings and replace NaN/NA values by empty
    # strings so Whoosh does not receive invalid values during indexing.
    df = pd.read_excel(excel_path, dtype=str).fillna("")

    with ix.writer(limitmb=256) as writer:
        for _, row in df.iterrows():
            pdf_file = row.get("PDF File")
            if pd.isna(pdf_file) or not pdf_file:
                continue
            pdf_path = Path(str(pdf_file))
            if not pdf_path.is_file():
                continue
            text = extract_text(pdf_path)
            writer.update_document(
                path=str(pdf_path),
                # parse_date returns ``None`` for invalid values which keeps the
                # field optional in the index.
                date=parse_date(row.get("Date", "")),
                registry=row.get("Registry", ""),
                parties=row.get("Parties", ""),
                court=row.get("Court", ""),
                action=row.get("Type of action", ""),
                content=text,
            )
    print(f"Indexed {len(df)} records from {excel_path}")


def do_search(args: argparse.Namespace) -> None:
    index_dir = Path(args.index_dir)
    if not index.exists_in(index_dir):
        raise SystemExit(f"Index directory not found: {index_dir}")

    ix = index.open_dir(index_dir)
    qp = MultifieldParser(
        ["content", "registry", "parties", "court", "action"], schema=ix.schema
    )
    query = qp.parse(args.query)
    results = []
    start_dt = parse_date(args.start) if args.start else None
    end_dt = parse_date(args.end) if args.end else None

    with ix.searcher() as searcher:
        q = query
        if start_dt or end_dt:
            range_q = DateRange("date", start_dt, end_dt)
            q = q & range_q
        for hit in searcher.search(q, limit=args.limit or None):
            record = {
                "path": hit["path"],
                "date": hit["date"].strftime("%Y-%m-%d") if hit["date"] else None,
                "registry": hit.get("registry"),
                "parties": hit.get("parties"),
                "court": hit.get("court"),
                "action": hit.get("action"),
            }
            results.append(record)
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Index and search PDF decisions")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Populate the search index")
    p_index.add_argument("--excel", default=DEFAULT_EXCEL, help="Excel metadata file")
    p_index.add_argument("--index-dir", default=DEFAULT_INDEX_DIR, help="Directory for index")
    p_index.set_defaults(func=do_index)

    p_search = sub.add_parser("search", help="Query the index")
    p_search.add_argument("--query", required=True, help="Text query")
    p_search.add_argument("--start", help="Start date DD/MM/YYYY")
    p_search.add_argument("--end", help="End date DD/MM/YYYY")
    p_search.add_argument("--limit", type=int, help="Maximum number of results")
    p_search.add_argument("--index-dir", default=DEFAULT_INDEX_DIR, help="Directory of index")
    p_search.set_defaults(func=do_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
