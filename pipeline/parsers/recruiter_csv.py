import csv
import os
from typing import List, Dict, Any

class RecruiterCSVParser:
    """
    Parses a standard recruiter CSV export into raw dictionaries.
    Expected columns (case-insensitive): name, email, phone, current_company, title.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    def parse(self) -> List[Dict[str, Any]]:
        """
        Reads the CSV and yields a list of dictionaries with attached provenance metadata.
        """
        if not os.path.exists(self.file_path):
            print(f"[CSV Parser] Error: File not found at {self.file_path}")
            return []

        raw_records = []

        with open(self.file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            # Normalize headers: lowercased and stripped to handle messy CSV formats
            if reader.fieldnames:
                reader.fieldnames = [str(name).strip().lower() for name in reader.fieldnames]

            for row_idx, row in enumerate(reader, start=2): # Start at 2 to account for header row
                # Robustness: Skip completely empty rows
                if not any(row.values()):
                    continue

                # Clean the values (strip whitespace, treat empty strings as None)
                cleaned_data = {}
                for key, val in row.items():
                    if not key:
                        continue # Skip columns with no header
                    clean_val = val.strip() if val and val.strip() != "" else None
                    cleaned_data[key] = clean_val

                # Skip if there is no identifying information
                if not cleaned_data.get('name') and not cleaned_data.get('email'):
                    print(f"[CSV Parser] Warning: Row {row_idx} lacks both name and email. Skipping.")
                    continue

                # Bundle the extracted data with its source metadata for the provenance tracker
                record_payload = {
                    "source_type": "structured",
                    "source_name": "recruiter_csv",
                    "file_name": os.path.basename(self.file_path),
                    "raw_data": cleaned_data
                }
                
                raw_records.append(record_payload)

        return raw_records

# --- Local Testing Block ---
if __name__ == "__main__":
    # Create a temporary dummy file to test the parser
    test_csv = "test_candidates.csv"
    with open(test_csv, "w", encoding="utf-8") as f:
        f.write("Name,Email,Phone,Current_Company,Title\n")
        f.write("Alice Smith,alice@example.com,555-0100,Tech Corp,Software Engineer\n")
        f.write("Bob Jones,,(555) 0101,Data Inc,Data Analyst\n") # Missing email
        f.write(",,,,\n") # Empty row
    
    parser = RecruiterCSVParser(test_csv)
    results = parser.parse()
    
    import json
    print(json.dumps(results, indent=2))
    
    # Clean up
    os.remove(test_csv)


"""

Key Design Choices Here
encoding='utf-8-sig': This handles the Byte Order Mark (BOM) that Microsoft Excel sometimes invisibly adds to the beginning of CSV files, which would otherwise corrupt your first header column (turning name into \ufeffname).

Header Normalization: reader.fieldnames is rewritten to lowercase and stripped of whitespace so you don't have to worry about whether the recruiter exported the file with Name, NAME, or name.

Encapsulation: Returning a dictionary with raw_data separated from source_name makes mapping provenance tags later in the pipeline incredibly clean.

"""