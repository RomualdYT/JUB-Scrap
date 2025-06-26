import argparse
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template_string
from whoosh import index
from whoosh.qparser import MultifieldParser
from whoosh.query import DateRange

DEFAULT_INDEX_DIR = Path("indexdir")

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>UPC Decisions Search</title>
</head>
<body>
  <h1>Search UPC Decisions</h1>
  <form method='get' action='/'>
    <input type='text' name='query' placeholder='keywords' value='{{ query|e }}'>
    <input type='text' name='start' placeholder='start DD/MM/YYYY' value='{{ start|e }}'>
    <input type='text' name='end' placeholder='end DD/MM/YYYY' value='{{ end|e }}'>
    <button type='submit'>Search</button>
  </form>
  {% if results %}
  <h2>Results</h2>
  <ul>
    {% for r in results %}
    <li>
      <strong>{{ r.date }}</strong> - {{ r.registry }} - {{ r.parties }} - {{ r.court }} - {{ r.action }}
      {% if r.path %}<a href='{{ r.path }}'>PDF</a>{% endif %}
    </li>
    {% endfor %}
  </ul>
  {% elif query %}
  <p>No results found.</p>
  {% endif %}
</body>
</html>
"""


def parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except Exception:
        return None


def create_app(index_dir: Path) -> Flask:
    if not index.exists_in(index_dir):
        raise SystemExit(f"Index directory not found: {index_dir}")
    ix = index.open_dir(index_dir)
    qp = MultifieldParser(
        ["content", "registry", "parties", "court", "action"], schema=ix.schema
    )

    @app.route("/", methods=["GET"])
    def search():
        query = request.args.get("query", "")
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        results = []
        if query:
            q = qp.parse(query)
            start_dt = parse_date(start)
            end_dt = parse_date(end)
            if start_dt or end_dt:
                q = q & DateRange("date", start_dt, end_dt)
            with ix.searcher() as searcher:
                for hit in searcher.search(q, limit=50):
                    results.append({
                        "date": hit.get("date").strftime("%Y-%m-%d") if hit.get("date") else "",
                        "registry": hit.get("registry", ""),
                        "parties": hit.get("parties", ""),
                        "court": hit.get("court", ""),
                        "action": hit.get("action", ""),
                        "path": hit.get("path", "")
                    })
        return render_template_string(TEMPLATE, query=query, start=start, end=end, results=results)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run web search interface")
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR, help="Index directory")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=5000, help="Port to serve on")
    args = parser.parse_args()
    application = create_app(Path(args.index_dir))
    application.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
