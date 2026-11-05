from pathlib import Path

from openpyxl import load_workbook

DOC = Path("docs/shopify_headers.md")
SOURCE = Path("data/private/products/Products.xlsx")

if "## Products export" in DOC.read_text(encoding="utf-8"):
    print("products section already in", DOC)
else:
    sheet = load_workbook(SOURCE, read_only=True).worksheets[0]
    header = [str(value) for value in next(sheet.iter_rows(values_only=True)) if value]
    lines = ["", f"## Products export ({len(header)} columns)", ""]
    lines.extend(f"- {name}" for name in header)
    with DOC.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("added", len(header), "product columns to", DOC)