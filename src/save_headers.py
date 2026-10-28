import csv
from pathlib import Path

PRIVATE = Path("data/private")
FILES = {
    "Orders export": PRIVATE / "order" / "Orders.csv",
    "Customers export": PRIVATE / "customer" / "Customers.csv",
}

lines = ["# Shopify export columns (names only, no data)", ""]
for title, path in FILES.items():
    with path.open(encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    lines.append(f"## {title} ({len(header)} columns)")
    lines.append("")
    lines.extend(f"- {name}" for name in header)
    lines.append("")

Path("docs/shopify_headers.md").write_text("\n".join(lines), encoding="utf-8")
print("saved docs/shopify_headers.md")