import camelot

tables = camelot.read_pdf(
    "data/raw/highmark_hdhp_ppoblue_2026.pdf",
    pages="2,3",
    flavor="lattice",
)

print(f"Found {len(tables)} table(s) across pages 2-3\n")

for i, table in enumerate(tables):
    print(f"--- Table {i} (page {table.page}, camelot's self-reported accuracy: {table.parsing_report['accuracy']}) ---")
    for row in table.df.values.tolist():
        print(row)
    print()