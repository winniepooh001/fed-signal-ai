#!/usr/bin/env python3
"""
TradingView Fields Extractor

Extracts field names and types from the TradingView Screener documentation
to help with filter validation and screener configuration.

Usage:
    python tradingview_fields_extractor.py
"""

import csv
import json
import re
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup


class TradingViewFieldsExtractor:
    """Extract field information from TradingView documentation"""

    def __init__(self):
        self.url = (
            "https://shner-elmo.github.io/TradingView-Screener/fields/stocks.html"
        )
        self.session = self._create_session()

    def _create_session(self):
        """Create a session with proper headers"""
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        return session

    def extract_fields(self) -> List[Dict[str, Any]]:
        """
        Extract field names and types from the documentation page

        Returns:
            List of dicts with 'field_name' and 'field_type' keys
        """

        print(f"Fetching data from: {self.url}")

        try:
            # Get the webpage
            response = self.session.get(self.url, timeout=15)
            response.raise_for_status()

            print(f"✅ Successfully fetched webpage (status: {response.status_code})")

            # Parse HTML
            soup = BeautifulSoup(response.content, "html.parser")

            # Find the table containing the fields
            tables = soup.find_all("table")
            print(f"Found {len(tables)} table(s) on the page")

            fields = []

            for table_idx, table in enumerate(tables):
                print(f"\nProcessing table {table_idx + 1}:")

                # Get all rows
                rows = table.find_all("tr")
                print(f"  Found {len(rows)} rows")

                # Skip header row if it exists
                data_rows = rows[1:] if len(rows) > 1 else rows

                for row_idx, row in enumerate(data_rows):
                    try:
                        # Get all cells in the row
                        cells = row.find_all(["td", "th"])

                        if len(cells) >= 3:  # Need at least 3 columns
                            # Extract field name (column 1) and type (column 3)
                            field_name = cells[0].get_text(strip=True)
                            field_type = cells[2].get_text(strip=True)

                            # Clean up the field name and type
                            field_name = self._clean_field_name(field_name)
                            field_type = self._clean_field_type(field_type)

                            # Skip empty or invalid entries
                            if (
                                field_name
                                and field_type
                                and field_name != "Field"
                                and field_type != "Type"
                            ):
                                field_info = {
                                    "field_name": field_name,
                                    "field_type": field_type,
                                    "table_index": table_idx,
                                    "row_index": row_idx,
                                }
                                fields.append(field_info)

                                # Debug output for first few fields
                                if len(fields) <= 5:
                                    print(
                                        f"    Row {row_idx + 1}: '{field_name}' -> '{field_type}'"
                                    )

                    except Exception as e:
                        print(f"    Error processing row {row_idx + 1}: {e}")
                        continue

                print(
                    f"  Extracted {len([f for f in fields if f['table_index'] == table_idx])} fields from this table"
                )

            print(f"\n✅ Total fields extracted: {len(fields)}")
            return fields

        except requests.RequestException as e:
            print(f"❌ Error fetching webpage: {e}")
            return []
        except Exception as e:
            print(f"❌ Error parsing webpage: {e}")
            return []

    def _clean_field_name(self, field_name: str) -> str:
        """Clean and normalize field name"""
        if not field_name:
            return ""

        # Remove extra whitespace and newlines
        cleaned = re.sub(r"\s+", " ", field_name.strip())

        # Remove any HTML artifacts
        cleaned = re.sub(r"<[^>]*>", "", cleaned)

        return cleaned

    def _clean_field_type(self, field_type: str) -> str:
        """Clean and normalize field type"""
        if not field_type:
            return ""

        # Remove extra whitespace and newlines
        cleaned = re.sub(r"\s+", " ", field_type.strip())

        # Remove any HTML artifacts
        cleaned = re.sub(r"<[^>]*>", "", cleaned)

        # Normalize common type names
        type_mapping = {
            "string": "string",
            "str": "string",
            "text": "string",
            "number": "number",
            "num": "number",
            "numeric": "number",
            "float": "number",
            "int": "number",
            "integer": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "date": "date",
            "datetime": "date",
        }

        cleaned_lower = cleaned.lower()
        for key, value in type_mapping.items():
            if key in cleaned_lower:
                return value

        return cleaned

    def save_to_json(
        self, fields: List[Dict[str, Any]], filename: str = "tradingview_fields.json"
    ):
        """Save fields to JSON file"""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(fields, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(fields)} fields to {filename}")
        except Exception as e:
            print(f"❌ Error saving JSON: {e}")

    def save_to_csv(
        self, fields: List[Dict[str, Any]], filename: str = "tradingview_fields.csv"
    ):
        """Save fields to CSV file"""
        try:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                if fields:
                    writer = csv.DictWriter(f, fieldnames=["field_name", "field_type"])
                    writer.writeheader()
                    for field in fields:
                        writer.writerow(
                            {
                                "field_name": field["field_name"],
                                "field_type": field["field_type"],
                            }
                        )
            print(f"✅ Saved {len(fields)} fields to {filename}")
        except Exception as e:
            print(f"❌ Error saving CSV: {e}")

    def print_field_summary(self, fields: List[Dict[str, Any]]):
        """Print a summary of extracted fields"""
        if not fields:
            print("No fields extracted")
            return

        print("\n📊 FIELD EXTRACTION SUMMARY")
        print("=" * 50)

        # Count by type
        type_counts = {}
        for field in fields:
            field_type = field["field_type"]
            type_counts[field_type] = type_counts.get(field_type, 0) + 1

        print(f"Total fields: {len(fields)}")
        print(f"Field types found: {len(type_counts)}")

        print("\nField type breakdown:")
        for field_type, count in sorted(type_counts.items()):
            print(f"  {field_type}: {count}")

        print("\nFirst 10 fields:")
        for i, field in enumerate(fields[:10], 1):
            print(f"  {i:2d}. {field['field_name']} ({field['field_type']})")

        if len(fields) > 10:
            print(f"  ... and {len(fields) - 10} more")

    def create_field_validator(
        self, fields: List[Dict[str, Any]], filename: str = "field_validator.py"
    ):
        """Create a Python module for field validation"""

        # Group fields by type
        fields_by_type = {}
        for field in fields:
            field_type = field["field_type"]
            if field_type not in fields_by_type:
                fields_by_type[field_type] = []
            fields_by_type[field_type].append(field["field_name"])

        # Generate Python code
        code = '''"""
TradingView Field Validator
Auto-generated from TradingView documentation

Usage:
    from field_validator import validate_field, get_field_type, VALID_FIELDS

    if validate_field('close'):
        print("Valid field")

    field_type = get_field_type('volume')
    print(f"Volume field type: {field_type}")
"""

from typing import Optional, Set, Dict, List

# All valid TradingView fields grouped by type
FIELDS_BY_TYPE: Dict[str, List[str]] = {
'''

        for field_type, field_list in sorted(fields_by_type.items()):
            code += f'    "{field_type}": [\n'
            for field_name in sorted(field_list):
                code += f'        "{field_name}",\n'
            code += "    ],\n"

        code += '''
}

# Flat set of all valid fields for quick lookup
VALID_FIELDS: Set[str] = set()
for field_list in FIELDS_BY_TYPE.values():
    VALID_FIELDS.update(field_list)

# Reverse mapping: field name -> type
FIELD_TYPE_MAP: Dict[str, str] = {}
for field_type, field_list in FIELDS_BY_TYPE.items():
    for field_name in field_list:
        FIELD_TYPE_MAP[field_name] = field_type


def validate_field(field_name: str) -> bool:
    """
    Check if a field name is valid for TradingView screeners

    Args:
        field_name: Field name to validate

    Returns:
        True if field is valid, False otherwise
    """
    return field_name in VALID_FIELDS


def get_field_type(field_name: str) -> Optional[str]:
    """
    Get the type of a TradingView field

    Args:
        field_name: Field name to look up

    Returns:
        Field type string or None if field not found
    """
    return FIELD_TYPE_MAP.get(field_name)


def get_fields_by_type(field_type: str) -> List[str]:
    """
    Get all fields of a specific type

    Args:
        field_type: Type to search for

    Returns:
        List of field names of that type
    """
    return FIELDS_BY_TYPE.get(field_type, [])


def get_numeric_fields() -> List[str]:
    """Get all numeric fields suitable for range/comparison filters"""
    return get_fields_by_type('number')


def get_string_fields() -> List[str]:
    """Get all string fields suitable for text/equality filters"""
    return get_fields_by_type('string')


def suggest_similar_fields(field_name: str, max_suggestions: int = 5) -> List[str]:
    """
    Suggest similar field names for typos/partial matches

    Args:
        field_name: Partial or misspelled field name
        max_suggestions: Maximum number of suggestions

    Returns:
        List of similar field names
    """
    field_lower = field_name.lower()
    suggestions = []

    # Exact substring matches first
    for valid_field in VALID_FIELDS:
        if field_lower in valid_field.lower():
            suggestions.append(valid_field)

    # Partial matches
    if len(suggestions) < max_suggestions:
        for valid_field in VALID_FIELDS:
            if any(part in valid_field.lower() for part in field_lower.split('_')):
                if valid_field not in suggestions:
                    suggestions.append(valid_field)

    return suggestions[:max_suggestions]


# Statistics
TOTAL_FIELDS = len(VALID_FIELDS)
FIELD_TYPE_COUNTS = {field_type: len(fields) for field_type, fields in FIELDS_BY_TYPE.items()}

if __name__ == "__main__":
    print(f"TradingView Field Validator")
    print(f"Total fields: {TOTAL_FIELDS}")
    print(f"Field types: {list(FIELDS_BY_TYPE.keys())}")

    # Test validation
    test_fields = ['close', 'volume', 'invalid_field', 'market_cap_basic']
    for field in test_fields:
        is_valid = validate_field(field)
        field_type = get_field_type(field)
        print(f"  {field}: {'✅' if is_valid else '❌'} ({field_type or 'unknown'})")
'''

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"✅ Created field validator module: {filename}")
        except Exception as e:
            print(f"❌ Error creating validator: {e}")


def main():
    """Main execution function"""
    print("🔍 TradingView Fields Extractor")
    print("=" * 50)

    # Create extractor
    extractor = TradingViewFieldsExtractor()

    # Extract fields
    fields = extractor.extract_fields()

    if not fields:
        print("❌ No fields extracted. Please check the website or network connection.")
        return

    # Print summary
    extractor.print_field_summary(fields)

    # Save results
    print("\n💾 SAVING RESULTS")
    print("-" * 30)

    extractor.save_to_json(fields)
    extractor.save_to_csv(fields)
    extractor.create_field_validator(fields)

    print("\n✅ Extraction completed successfully!")
    print(f"   Fields extracted: {len(fields)}")
    print(
        "   Files created: tradingview_fields.json, tradingview_fields.csv, field_validator.py"
    )


if __name__ == "__main__":
    main()
