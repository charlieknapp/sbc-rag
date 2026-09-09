import pdfplumber

TUNED_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 8,
    "join_tolerance": 8,
    "intersection_tolerance": 8,
    "edge_min_length": 10,
}

with pdfplumber.open("data/raw/highmark_hdhp_ppoblue_2026.pdf") as pdf:
    for page_index in [1, 2]:  # pages 2 and 3
        page = pdf.pages[page_index]

        default_tables = page.extract_tables()
        tuned_tables = page.extract_tables(table_settings=TUNED_SETTINGS)

        print(f"=== Page {page_index + 1} ===")
        print(f"Default settings: {len(default_tables)} table(s)")
        print(f"Tuned settings:   {len(tuned_tables)} table(s)\n")

        print("--- Tuned output ---")
        for i, table in enumerate(tuned_tables):
            print(f"--- Table {i} ---")
            for row in table:
                print(row)
            print()