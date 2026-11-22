import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from inventory_engine import (
    InventoryValidationError,
    analyze_inventory,
    list_workbook_sheets,
    suggest_inventory_sheet,
    validate_inventory_csv,
    validate_inventory_file,
)

CANONICAL_HEADER = (
    "product,current_stock,avg_daily_sales,unit_cost,lead_time_days\n"
)


def _workbook_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        worksheet = workbook.create_sheet(name)
        for row in rows:
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_renamed_headers_are_mapped_and_ignored_columns_are_reported():
    csv_data = (
        "Item Description,Qty on Hand,Avg. Units per Day,Cost Price (R),"
        "Supplier Lead Time (Days),Category\n"
        "Body Lotion,8,1.5,72.50,4,Skincare\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert frame.loc[0, "product"] == "Body Lotion"
    assert frame.loc[0, "current_stock"] == 8
    assert frame.loc[0, "avg_daily_sales"] == 1.5
    assert frame.loc[0, "unit_cost"] == Decimal("72.50")
    assert frame.loc[0, "lead_time_days"] == 4
    assert frame.attrs["column_mapping"] == {
        "product": "Item Description",
        "current_stock": "Qty on Hand",
        "avg_daily_sales": "Avg. Units per Day",
        "unit_cost": "Cost Price (R)",
        "lead_time_days": "Supplier Lead Time (Days)",
    }
    assert frame.attrs["ignored_columns"] == ["Category"]


def test_reordered_headers_keep_the_correct_values():
    csv_data = (
        "lead_time_days,unit_cost,avg_daily_sales,current_stock,product\n"
        "3,10.50,2,7,Lip Balm\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert frame.loc[0, "product"] == "Lip Balm"
    assert frame.loc[0, "current_stock"] == 7
    assert frame.loc[0, "avg_daily_sales"] == 2
    assert frame.loc[0, "unit_cost"] == Decimal("10.50")
    assert frame.loc[0, "lead_time_days"] == 3


def test_header_row_is_found_below_title_rows():
    csv_data = (
        "Stock report,,\n"
        "As at March 2026,,\n"
        ",,\n"
        "Product,Stock,Daily Sales,Unit Cost,Lead Time\n"
        "Lotion,8,1.5,72.50,4\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert frame.attrs["header_row"] == 4
    assert frame.loc[0, "product"] == "Lotion"
    assert frame.loc[0, "lead_time_days"] == 4


def test_semicolon_csv_with_decimal_commas_is_parsed():
    csv_data = (
        "Product;Stock;Avg Units per Day;Unit Cost;Lead Time\n"
        "Lotion;8;1,5;72,50;4\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert frame.loc[0, "avg_daily_sales"] == 1.5
    assert frame.loc[0, "unit_cost"] == Decimal("72.50")


def test_currency_symbols_and_thousands_separators_are_cleaned():
    csv_data = (
        "product;current_stock;avg_daily_sales;unit_cost;lead_time_days\n"
        "Lotion;1 234;2,5;R 1 234,50;7\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert frame.loc[0, "current_stock"] == 1234
    assert frame.loc[0, "avg_daily_sales"] == 2.5
    assert frame.loc[0, "unit_cost"] == Decimal("1234.50")


def test_windows_encoded_csv_is_decoded():
    csv_data = (
        "product,current_stock,avg_daily_sales,unit_cost,lead_time_days\n"
        "Café Crème,5,1,10,3\n"
    ).encode("cp1252")

    frame = validate_inventory_csv(csv_data)

    assert frame.loc[0, "product"] == "Café Crème"
    assert frame.attrs["encoding"] == "cp1252"


def test_xlsx_single_sheet_is_parsed_with_mapping_metadata():
    data = _workbook_bytes(
        {
            "Inventory": [
                ["Item", "Qty", "Daily Sales", "Cost", "Lead Time"],
                ["Body Lotion", 8, 1.5, 72.5, 4],
            ]
        }
    )

    frame = validate_inventory_file(data, "stock.xlsx")

    assert frame.attrs["sheet_name"] == "Inventory"
    assert frame.attrs["file_type"] == "xlsx"
    assert frame.loc[0, "product"] == "Body Lotion"
    assert frame.loc[0, "current_stock"] == 8
    assert frame.attrs["column_mapping"]["current_stock"] == "Qty"


def test_multi_sheet_workbook_lists_sheets_and_auto_selects_the_stock_sheet():
    data = _workbook_bytes(
        {
            "Instructions": [["How to use this template"], ["Step 1"]],
            "Stock": [
                ["Product", "Stock", "Daily Sales", "Unit Cost", "Lead Time"],
                ["Body Lotion", 8, 1.5, 72.5, 4],
            ],
        }
    )

    assert list_workbook_sheets(data, "stock.xlsx") == ["Instructions", "Stock"]
    assert suggest_inventory_sheet(data, "stock.xlsx") == "Stock"

    frame = validate_inventory_file(data, "stock.xlsx")

    assert frame.attrs["sheet_name"] == "Stock"
    assert frame.loc[0, "product"] == "Body Lotion"


def test_multiple_inventory_sheets_require_an_explicit_choice():
    data = _workbook_bytes(
        {
            "January": [
                ["Product", "Stock", "Daily Sales", "Unit Cost", "Lead Time"],
                ["Lotion", 8, 1.5, 72.5, 4],
            ],
            "February": [
                ["Product", "Stock", "Daily Sales", "Unit Cost", "Lead Time"],
                ["Lotion", 6, 1.5, 72.5, 4],
            ],
        }
    )

    with pytest.raises(InventoryValidationError, match="multiple worksheets"):
        validate_inventory_file(data, "stock.xlsx")

    frame = validate_inventory_file(data, "stock.xlsx", sheet_name="February")
    assert frame.loc[0, "current_stock"] == 6


def test_two_headers_that_match_one_field_are_rejected_as_ambiguous():
    csv_data = (
        "Product,Product Name,Stock,Daily Sales,Unit Cost,Lead Time\n"
        "Lotion,Lotion,8,1.5,72.5,4\n"
    ).encode()

    with pytest.raises(InventoryValidationError, match="ambiguous"):
        validate_inventory_csv(csv_data)


def test_missing_renamed_field_reports_the_schema_name():
    csv_data = "Item,Qty,Daily Sales,Cost\nLotion,8,1.5,72.5\n".encode()

    with pytest.raises(
        InventoryValidationError, match="Missing required column.*lead_time_days"
    ):
        validate_inventory_csv(csv_data)


def test_weekly_sales_column_gets_a_conversion_hint():
    csv_data = (
        "Product,Stock,Weekly Sales,Unit Cost,Lead Time\n"
        "Lotion,8,10,72.5,4\n"
    ).encode()

    with pytest.raises(InventoryValidationError, match="average daily unit sales"):
        validate_inventory_csv(csv_data)


def test_stock_value_column_is_not_used_as_a_unit_count():
    csv_data = (
        "Product,Stock Value,Daily Sales,Unit Cost,Lead Time\n"
        "Lotion,600,1.5,72.5,4\n"
    ).encode()

    with pytest.raises(InventoryValidationError, match="units on hand"):
        validate_inventory_csv(csv_data)


def test_total_cost_column_is_not_used_as_a_unit_cost():
    csv_data = (
        "Product,Stock,Daily Sales,Total Cost,Lead Time\n"
        "Lotion,8,1.5,600,4\n"
    ).encode()

    with pytest.raises(InventoryValidationError, match="per-unit cost"):
        validate_inventory_csv(csv_data)


def test_descriptive_columns_are_not_mistaken_for_quantities_or_names():
    csv_data = (
        "Product Category,SKU,Stock On Order,Qty On Hand,Daily Sales,"
        "Unit Cost,Lead Time\n"
        "Skincare,BODY-001,20,8,1.5,72.5,4\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert frame.attrs["column_mapping"]["product"] == "SKU"
    assert frame.attrs["column_mapping"]["current_stock"] == "Qty On Hand"
    assert frame.attrs["ignored_columns"] == ["Product Category", "Stock On Order"]


def test_trailing_total_row_is_skipped():
    csv_data = (
        CANONICAL_HEADER
        + "Lotion,8,1.5,72.5,4\n"
        + "TOTAL,8,1.5,580,4\n"
    ).encode()

    frame = validate_inventory_csv(csv_data)

    assert len(frame) == 1
    assert frame.loc[0, "product"] == "Lotion"
    assert frame.attrs["skipped_total_rows"] == [3]


def test_invalid_workbook_reports_a_friendly_error():
    with pytest.raises(InventoryValidationError, match="workbook could not be read"):
        validate_inventory_file(b"not a real workbook", "broken.xlsx")


def test_unsupported_file_extension_is_rejected():
    with pytest.raises(InventoryValidationError, match="Unsupported file type"):
        validate_inventory_file(CANONICAL_HEADER.encode(), "stock.txt")


def test_mapped_file_produces_the_same_analysis_as_a_canonical_file():
    canonical = validate_inventory_csv(
        (CANONICAL_HEADER + "Lotion,8,1.5,72.5,4\n").encode()
    )
    mapped = validate_inventory_csv(
        (
            "Item Description,Qty on Hand,Avg. Units per Day,Cost Price,"
            "Supplier Lead Time\n"
            "Lotion,8,1.5,72.5,4\n"
        ).encode()
    )

    assert analyze_inventory(canonical) == analyze_inventory(mapped)
