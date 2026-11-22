import io

import pytest
from openpyxl import Workbook

from inventory_engine import (
    InventoryValidationError,
    inspect_inventory_file,
    validate_inventory_file,
)

AMBIGUOUS_CSV = (
    "Product,Product Name,Stock,Daily Sales,Unit Cost,Lead Time\n"
    "Lotion,Lotion,8,1.5,72.5,4\n"
).encode()

AMBIGUOUS_MAPPING = {
    "product": "Product Name",
    "current_stock": "Stock",
    "avg_daily_sales": "Daily Sales",
    "unit_cost": "Unit Cost",
    "lead_time_days": "Lead Time",
}


def test_inspection_reports_the_ambiguous_column_and_preview_rows():
    report = inspect_inventory_file(AMBIGUOUS_CSV, "stock.csv")

    assert report["is_ready"] is False
    assert report["missing_fields"] == ["product"]
    assert any("Product" in problem and "Product Name" in problem for problem in report["problems"])
    assert [candidate["source"] for candidate in report["candidates"]["product"]] == [
        "Product",
        "Product Name",
    ]
    assert report["suggested_mapping"]["current_stock"] == 2
    assert report["sample_rows"] == [["Lotion", "Lotion", "8", "1.5", "72.5", "4"]]
    assert report["header_row"] == 1


def test_explicit_mapping_resolves_an_ambiguous_header():
    frame = validate_inventory_file(
        AMBIGUOUS_CSV, "stock.csv", column_mapping=AMBIGUOUS_MAPPING
    )

    assert frame.loc[0, "product"] == "Lotion"
    assert frame.loc[0, "current_stock"] == 8
    assert frame.attrs["column_mapping"]["product"] == "Product Name"
    assert frame.attrs["mapping_details"]["product"]["method"] == "confirmed"


def test_explicit_mapping_accepts_case_insensitive_header_names():
    mapping = {**AMBIGUOUS_MAPPING, "product": "product name"}

    frame = validate_inventory_file(AMBIGUOUS_CSV, "stock.csv", column_mapping=mapping)

    assert frame.loc[0, "product"] == "Lotion"
    assert frame.attrs["column_mapping"]["product"] == "Product Name"


def test_explicit_mapping_can_use_headers_the_matcher_does_not_recognise():
    header = "AAA,BBB,CCC,DDD,EEE\nLotion,8,1.5,72.5,4\n".encode()
    mapping = {
        "product": "AAA",
        "current_stock": "BBB",
        "avg_daily_sales": "CCC",
        "unit_cost": "DDD",
        "lead_time_days": "EEE",
    }

    report = inspect_inventory_file(header, "unknown.csv")
    assert report["is_ready"] is False
    assert report["suggested_mapping"] == {}

    frame = validate_inventory_file(header, "unknown.csv", column_mapping=mapping)
    assert frame.loc[0, "product"] == "Lotion"
    assert frame.loc[0, "lead_time_days"] == 4


def test_explicit_mapping_requires_every_field():
    mapping = dict(AMBIGUOUS_MAPPING)
    mapping.pop("lead_time_days")

    with pytest.raises(InventoryValidationError, match="Choose a column for: lead_time_days"):
        validate_inventory_file(AMBIGUOUS_CSV, "stock.csv", column_mapping=mapping)


def test_explicit_mapping_rejects_a_column_that_is_not_in_the_header_row():
    mapping = {**AMBIGUOUS_MAPPING, "product": "Not a column"}

    with pytest.raises(InventoryValidationError, match="was not found"):
        validate_inventory_file(AMBIGUOUS_CSV, "stock.csv", column_mapping=mapping)


def test_explicit_mapping_rejects_one_column_for_two_fields():
    mapping = {**AMBIGUOUS_MAPPING, "current_stock": "Product Name"}

    with pytest.raises(InventoryValidationError, match="cannot supply"):
        validate_inventory_file(AMBIGUOUS_CSV, "stock.csv", column_mapping=mapping)


def test_explicit_mapping_still_blocks_a_stock_value_column():
    csv_data = (
        "Product,Stock Value,Daily Sales,Unit Cost,Lead Time\n"
        "Lotion,600,1.5,72.5,4\n"
    ).encode()
    mapping = {
        "product": "Product",
        "current_stock": "Stock Value",
        "avg_daily_sales": "Daily Sales",
        "unit_cost": "Unit Cost",
        "lead_time_days": "Lead Time",
    }

    with pytest.raises(InventoryValidationError, match="monetary value"):
        validate_inventory_file(csv_data, "stock.csv", column_mapping=mapping)


def test_explicit_mapping_still_blocks_weekly_sales():
    csv_data = (
        "Product,Stock,Daily Sales,Unit Cost,Weekly Sales\n"
        "Lotion,8,1.5,72.5,10\n"
    ).encode()
    mapping = {
        "product": "Product",
        "current_stock": "Stock",
        "avg_daily_sales": "Weekly Sales",
        "unit_cost": "Unit Cost",
        "lead_time_days": "Unit Cost",
    }

    with pytest.raises(InventoryValidationError, match="average daily unit sales"):
        validate_inventory_file(csv_data, "stock.csv", column_mapping=mapping)


def test_canonical_file_needs_no_confirmation():
    report = inspect_inventory_file(
        b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\n"
        b"Lotion,8,1.5,72.5,4\n",
        "stock.csv",
    )

    assert report["is_ready"] is True
    assert report["problems"] == []
    assert report["missing_fields"] == []
    assert report["suggested_mapping"] == {
        "product": 0,
        "current_stock": 1,
        "avg_daily_sales": 2,
        "unit_cost": 3,
        "lead_time_days": 4,
    }


def test_explicit_mapping_works_for_a_selected_workbook_sheet():
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheet = workbook.create_sheet("Stock")
    sheet.append(["Report", "", "", "", ""])
    sheet.append(["Part No", "On Hand", "Rate", "Cost", "Wait"])
    sheet.append(["BODY-001", 8, 1.5, 72.5, 4])
    buffer = io.BytesIO()
    workbook.save(buffer)
    data = buffer.getvalue()

    report = inspect_inventory_file(data, "stock.xlsx", sheet_name="Stock")
    assert report["sheet_name"] == "Stock"
    assert report["available_sheets"] == ["Stock"]
    assert report["header_row"] == 2

    mapping = {
        "product": "Part No",
        "current_stock": "On Hand",
        "avg_daily_sales": "Rate",
        "unit_cost": "Cost",
        "lead_time_days": "Wait",
    }
    frame = validate_inventory_file(
        data, "stock.xlsx", sheet_name="Stock", column_mapping=mapping
    )
    assert frame.loc[0, "product"] == "BODY-001"
    assert frame.loc[0, "unit_cost"] == pytest.approx(72.5)
    assert frame.attrs["sheet_name"] == "Stock"

    mapping["unit_cost"] = "Rate"
    with pytest.raises(InventoryValidationError, match="cannot supply"):
        validate_inventory_file(
            data, "stock.xlsx", sheet_name="Stock", column_mapping=mapping
        )
