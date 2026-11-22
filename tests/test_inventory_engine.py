from decimal import Decimal

import pytest

from inventory_engine import (
    analyze_inventory,
    get_product_details,
    get_priority_products,
    validate_inventory_csv,
)


REGRESSION_CSV = b"""product,current_stock,avg_daily_sales,unit_cost,lead_time_days
Milk,8,6,18,2
Bread,5,10,15,1
Rice,30,3,25,4
Sugar,12,5,20,3
Cooking Oil,20,2,45,5
"""


@pytest.fixture
def regression_analysis():
    return analyze_inventory(validate_inventory_csv(REGRESSION_CSV))


def test_inventory_value_regression(regression_analysis):
    assert regression_analysis["summary"]["total_inventory_value"] == Decimal("2109.00")


def test_stock_coverage_regression(regression_analysis):
    coverage = {
        product["product"]: product["stock_coverage_days"]
        for product in regression_analysis["products"]
    }
    assert coverage == pytest.approx(
        {"Milk": 8 / 6, "Bread": 0.5, "Rice": 10, "Sugar": 2.4, "Cooking Oil": 10}
    )


def test_regression_statuses(regression_analysis):
    statuses = {p["product"]: p["status"] for p in regression_analysis["products"]}
    assert statuses == {
        "Milk": "SHORTAGE RISK",
        "Bread": "SHORTAGE RISK",
        "Rice": "HEALTHY",
        "Sugar": "SHORTAGE RISK",
        "Cooking Oil": "HEALTHY",
    }


def test_reorder_point_is_demand_times_lead_time(regression_analysis):
    products = {p["product"]: p for p in regression_analysis["products"]}
    assert products["Milk"]["reorder_point"] == 12
    assert products["Sugar"]["lead_time_demand"] == 15


def test_exact_reorder_threshold_triggers_reorder_now():
    data = b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nExact,6,2,10,3\n"
    product = analyze_inventory(validate_inventory_csv(data))["products"][0]
    assert product["status"] == "REORDER NOW"


def test_out_of_stock_with_demand_is_urgent():
    data = b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nEmpty,0,1,10,3\n"
    product = analyze_inventory(validate_inventory_csv(data))["products"][0]
    assert product["status"] == "OUT OF STOCK"


def test_zero_demand_has_no_fabricated_coverage():
    data = b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nIdle,0,0,10,3\n"
    product = analyze_inventory(validate_inventory_csv(data))["products"][0]
    assert product["status"] == "NO RECORDED DEMAND"
    assert product["stock_coverage_days"] is None


def test_priority_order_is_deterministic_and_urgent_first():
    data = b"""product,current_stock,avg_daily_sales,unit_cost,lead_time_days
Healthy,10,1,10,2
Short,1,1,10,3
Empty,0,1,10,1
Exact,2,1,10,2
No Demand,5,0,10,3
"""
    ordered = [
        p["product"]
        for p in get_priority_products(analyze_inventory(validate_inventory_csv(data)))
    ]
    assert ordered == ["Empty", "Short", "Exact"]


def test_missing_product_returns_structured_not_found(regression_analysis):
    result = get_product_details(regression_analysis, "Imaginary serum")
    assert result["found"] is False
    assert "not present" in result["error"]


def test_sample_dataset_has_expected_demo_cases():
    from pathlib import Path

    data = Path(__file__).parents[1] / "data" / "sample_inventory.csv"
    analysis = analyze_inventory(validate_inventory_csv(data.read_bytes()))
    statuses = {p["product"]: p["status"] for p in analysis["products"]}
    assert len(statuses) == 15
    assert statuses["Lip Gloss"] == "REORDER NOW"
    assert statuses["Sunscreen"] == "OUT OF STOCK"
    assert statuses["Lip Balm"] == "NO RECORDED DEMAND"
