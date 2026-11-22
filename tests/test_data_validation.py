import pytest

from inventory_engine import InventoryValidationError, validate_inventory_csv

HEADER = "product,current_stock,avg_daily_sales,unit_cost,lead_time_days\n"


@pytest.mark.parametrize(
    "csv_data, message",
    [
        (
            b"product,current_stock,avg_daily_sales,unit_cost\nBody Lotion,2,1,10\n",
            "Missing required column",
        ),
        (
            (HEADER + "Lotion,-1,1,10,2\n").encode(),
            "current_stock cannot be negative",
        ),
        (
            (HEADER + "Lotion,2.5,1,10,2\n").encode(),
            "current_stock must be a whole number",
        ),
        (
            (HEADER + "Lotion,2,NaN,10,2\n").encode(),
            "avg_daily_sales must be finite",
        ),
        (
            (HEADER + "Lotion,2,one,10,2\n").encode(),
            "avg_daily_sales must be a number",
        ),
        (
            (HEADER + "Lotion,2,1,,2\n").encode(),
            "unit_cost is required",
        ),
        (
            (HEADER + "   ,2,1,10,2\n").encode(),
            "Product names cannot be empty",
        ),
        (
            (HEADER + "Lotion,2,1,10,2\n lotion  ,3,1,10,2\n").encode(),
            "Product names must be unique",
        ),
    ],
)
def test_invalid_csv_is_rejected_with_actionable_message(csv_data, message):
    with pytest.raises(InventoryValidationError, match=message):
        validate_inventory_csv(csv_data)


def test_empty_file_is_rejected():
    with pytest.raises(InventoryValidationError, match="empty"):
        validate_inventory_csv(b"")


def test_header_only_csv_is_rejected():
    with pytest.raises(InventoryValidationError, match="no product rows"):
        validate_inventory_csv(HEADER.encode())


def test_malformed_csv_is_rejected():
    with pytest.raises(InventoryValidationError):
        validate_inventory_csv((HEADER + '"Broken,2,1,10,2\n').encode())


def test_duplicate_column_names_are_rejected_before_pandas_renames_them():
    csv_data = (
        b"product,product,current_stock,avg_daily_sales,unit_cost,lead_time_days\n"
        b"Lotion,Lotion,2,1,10,2\n"
    )
    with pytest.raises(InventoryValidationError, match="duplicate column names"):
        validate_inventory_csv(csv_data)


def test_whitespace_only_file_reports_missing_header_and_data():
    with pytest.raises(InventoryValidationError, match="no header or data"):
        validate_inventory_csv(b"   \n\n  ")


def test_extremely_large_values_are_rejected_with_a_friendly_message():
    csv_data = (
        HEADER + "Huge,100000000000000000000,1,100000000000000000000,2\n"
    ).encode()
    with pytest.raises(InventoryValidationError, match="too large"):
        validate_inventory_csv(csv_data)


def test_positive_demand_that_underflows_float_is_rejected():
    csv_data = (HEADER + "Tiny,1,1e-1000,1,1\n").encode()
    with pytest.raises(InventoryValidationError, match="too small to represent safely"):
        validate_inventory_csv(csv_data)
