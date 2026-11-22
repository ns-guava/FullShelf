"""Inventory file validation and deterministic calculations for FullShelf."""

from __future__ import annotations

import csv
import difflib
import io
import logging
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = (
    "product",
    "current_stock",
    "avg_daily_sales",
    "unit_cost",
    "lead_time_days",
)
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1_000
MAX_NUMERIC_VALUE = Decimal("1e12")
COMPARISON_TOLERANCE = 1e-9
CENT = Decimal("0.01")

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")
MAX_HEADER_SCAN_ROWS = 25
MIN_MAPPING_SCORE = 78
AMBIGUITY_SCORE_DELTA = 2

_ABBREVIATIONS = {
    "qty": "quantity",
    "qnty": "quantity",
    "avg": "average",
    "av": "average",
    "desc": "description",
    "dsc": "description",
    "no": "number",
    "nos": "numbers",
    "amt": "amount",
    "val": "value",
    "pcs": "units",
    "pc": "units",
    "ea": "each",
    "wks": "weeks",
    "wk": "weeks",
    "mths": "months",
    "mth": "months",
    "yrs": "years",
    "yr": "years",
}
_SINGULAR = {
    "items": "item",
    "products": "product",
    "units": "unit",
    "days": "day",
    "weeks": "week",
    "months": "month",
    "years": "year",
    "prices": "price",
    "costs": "cost",
    "quantities": "quantity",
    "numbers": "number",
    "values": "value",
    "totals": "total",
    "skus": "sku",
}
_CURRENCY_TOKENS = {"r", "zar", "usd", "eur", "gbp"}

_RAW_ALIASES: dict[str, tuple[tuple[str, int], ...]] = {
    "product": (
        ("product", 100),
        ("product name", 100),
        ("item name", 96),
        ("item description", 96),
        ("product description", 96),
        ("product title", 94),
        ("name", 92),
        ("item", 90),
        ("stock item", 90),
        ("description", 86),
        ("sku", 84),
        ("sku code", 84),
        ("product code", 84),
        ("item code", 84),
        ("barcode", 82),
        ("article", 82),
        ("product id", 82),
        ("item id", 82),
        ("goods", 82),
        ("title", 80),
        ("item number", 80),
        ("code", 78),
        ("merchandise", 78),
    ),
    "current_stock": (
        ("current stock", 100),
        ("stock on hand", 99),
        ("qty on hand", 98),
        ("quantity on hand", 98),
        ("stock", 96),
        ("on hand", 94),
        ("units on hand", 94),
        ("inventory on hand", 94),
        ("current inventory", 92),
        ("available stock", 92),
        ("quantity available", 92),
        ("qty available", 92),
        ("stock available", 92),
        ("physical stock", 92),
        ("in stock", 90),
        ("current quantity", 90),
        ("onhand", 90),
        ("closing stock", 90),
        ("stock level", 88),
        ("stock qty", 88),
        ("stock quantity", 88),
        ("quantity in stock", 88),
        ("units in stock", 88),
        ("stock balance", 88),
        ("qty", 86),
        ("quantity", 86),
        ("stock count", 86),
        ("units", 84),
        ("inventory", 84),
    ),
    "avg_daily_sales": (
        ("avg daily sales", 100),
        ("average daily sales", 100),
        ("daily sales", 98),
        ("daily demand", 98),
        ("average daily demand", 98),
        ("units per day", 96),
        ("sales per day", 96),
        ("demand per day", 96),
        ("daily units sold", 96),
        ("average units per day", 96),
        ("units sold per day", 96),
        ("average daily movement", 94),
        ("daily usage", 94),
        ("average daily usage", 94),
        ("daily unit", 94),
        ("daily movement", 92),
        ("movement per day", 90),
        ("daily average", 86),
        ("average sales", 86),
        ("sales", 84),
        ("demand", 84),
        ("units sold", 82),
        ("usage", 80),
        ("sold", 78),
    ),
    "unit_cost": (
        ("unit cost", 100),
        ("cost per unit", 100),
        ("cost price", 98),
        ("purchase price", 98),
        ("buy price", 98),
        ("buying price", 98),
        ("unit price", 96),
        ("supplier cost", 96),
        ("price per unit", 96),
        ("purchase cost", 96),
        ("cost each", 94),
        ("unit purchase cost", 94),
        ("unit cost price", 94),
        ("cost ex vat", 92),
        ("cost excl vat", 92),
        ("unit cost ex vat", 92),
        ("unit cost excl vat", 92),
        ("cost including vat", 90),
        ("cost incl vat", 90),
        ("unit cost incl vat", 90),
        ("landed cost", 90),
        ("wholesale price", 88),
        ("cost", 86),
        ("price", 82),
    ),
    "lead_time_days": (
        ("lead time", 100),
        ("lead time day", 100),
        ("supplier lead time", 98),
        ("delivery lead time", 98),
        ("delivery day", 98),
        ("supplier delivery day", 96),
        ("replenishment day", 96),
        ("order lead time", 96),
        ("restock lead time", 96),
        ("average lead time", 96),
        ("day to deliver", 94),
        ("restock day", 94),
        ("replenish day", 94),
        ("lead day", 88),
        ("leadtime", 90),
        ("time to deliver", 90),
        ("delivery time", 84),
        ("replenishment time", 84),
        ("delivery", 82),
        ("replenish", 82),
    ),
}


def _normalise_header(value: Any) -> str:
    """Lowercase a header, expand abbreviations, and strip units and punctuation."""
    text = "" if value is None else str(value)
    text = text.replace("\ufeff", "").strip()
    if not text:
        return ""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = text.casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}", " ", text)
    text = text.replace("%", " percent ").replace("/", " per ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens: list[str] = []
    for token in text.split():
        token = _ABBREVIATIONS.get(token, token)
        token = _SINGULAR.get(token, token)
        if token in _CURRENCY_TOKENS:
            continue
        tokens.append(token)
    return " ".join(tokens)


FIELD_ALIASES = {
    field: tuple((_normalise_header(alias), weight) for alias, weight in aliases)
    for field, aliases in _RAW_ALIASES.items()
}


_BLOCKED_TOKENS = {
    "product": {
        "value",
        "cost",
        "price",
        "total",
        "amount",
        "category",
        "type",
        "group",
        "class",
        "brand",
        "department",
        "supplier",
        "weight",
        "height",
        "width",
        "size",
        "colour",
        "color",
        "dimension",
        "dimensions",
        "uom",
        "unit",
        "location",
        "warehouse",
        "status",
    },
    "current_stock": {
        "value",
        "cost",
        "price",
        "amount",
        "total",
        "revenue",
        "sales",
        "extended",
        "cogs",
        "category",
        "type",
        "group",
        "class",
        "brand",
        "supplier",
        "location",
        "warehouse",
        "bin",
        "aisle",
        "status",
        "order",
        "incoming",
        "reserved",
        "committed",
        "adjustment",
        "adjustments",
        "date",
        "opening",
        "average",
        "movement",
        "turnover",
        "cover",
        "day",
        "uom",
        "measure",
    },
    "avg_daily_sales": {
        "percent",
        "percentage",
        "category",
        "type",
        "group",
        "class",
        "rep",
        "representative",
        "tax",
        "region",
        "channel",
        "status",
        "person",
        "target",
    },
    "unit_cost": {
        "total",
        "value",
        "amount",
        "extended",
        "cogs",
        "selling",
        "retail",
        "rsp",
        "rrp",
        "margin",
        "markup",
        "stock",
        "sales",
        "category",
        "type",
        "group",
        "class",
        "code",
        "list",
        "centre",
        "center",
        "currency",
        "date",
    },
    "lead_time_days": {
        "shelf",
        "expiry",
        "expire",
        "warranty",
        "age",
        "credit",
        "address",
        "date",
        "status",
        "note",
        "notes",
        "fee",
        "cost",
        "charge",
        "method",
        "company",
        "instruction",
        "instructions",
    },
}

_TOTAL_LABELS = {
    "total",
    "totals",
    "grand total",
    "subtotal",
    "sub total",
    "sum",
    "overall total",
    "total stock",
    "total inventory",
    "total value",
    "total cost",
}


class InventoryValidationError(ValueError):
    """Raised when an uploaded inventory file cannot be safely analysed."""


def _period_hint(header: Any) -> str | None:
    """Return the reporting period implied by a header, if any."""
    text = ("" if header is None else str(header)).casefold()
    if not text.strip():
        return None
    if re.search(
        r"\b(?:last|past|previous|trailing)\s+\d+\s*(?:day|week|month|year)s?\b",
        text,
    ):
        return "period total"
    if re.search(r"\b\d+\s*(?:day|week|month|year)s?\b", text):
        return "period total"
    if re.search(r"\b(?:daily|per day|a day|/\s*day)\b", text):
        return "day"
    if re.search(r"\b(?:weekly|per week|a week|/\s*week|weeks?)\b", text):
        return "week"
    if re.search(r"\b(?:monthly|per month|a month|/\s*month|months?)\b", text):
        return "month"
    if re.search(r"\b(?:quarterly|per quarter|quarters?)\b", text):
        return "quarter"
    if re.search(r"\b(?:yearly|annual|annually|per year|years?)\b", text):
        return "year"
    return None


def _score_header(header: Any, field: str) -> tuple[int, str]:
    """Score one header against one required field, returning (score, method)."""
    normalised = _normalise_header(header)
    if not normalised:
        return 0, "empty"
    tokens = set(normalised.split())
    if tokens & _BLOCKED_TOKENS.get(field, set()):
        return 0, "blocked"
    period = _period_hint(header)
    if field == "avg_daily_sales" and period not in (None, "day"):
        return 0, "blocked"
    if field == "lead_time_days" and period not in (None, "day"):
        return 0, "blocked"

    best_score = 0
    best_method = "none"
    compact = normalised.replace(" ", "")
    for alias, weight in FIELD_ALIASES[field]:
        alias_tokens = set(alias.split())
        if normalised == alias:
            if weight > best_score:
                best_score, best_method = weight, "exact"
            continue
        if alias_tokens and alias_tokens <= tokens:
            extra = len(tokens - alias_tokens)
            score = weight - min(16, 4 * extra)
            if score > best_score:
                best_score, best_method = score, "words"
        alias_compact = alias.replace(" ", "")
        if len(compact) >= 4 and len(alias_compact) >= 4:
            ratio = difflib.SequenceMatcher(None, compact, alias_compact).ratio()
            if ratio >= 0.9:
                score = int(round(weight * ratio)) - 6
                if score > best_score:
                    best_score, best_method = score, "fuzzy"
    if best_score < MIN_MAPPING_SCORE:
        return 0, "unmapped"
    return best_score, best_method


def _collect_mapping(
    headers: list[str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Map canonical fields to header columns without guessing ties."""
    candidates: dict[str, list[dict[str, Any]]] = {
        field: [] for field in REQUIRED_COLUMNS
    }
    for index, header in enumerate(headers):
        for field in REQUIRED_COLUMNS:
            score, method = _score_header(header, field)
            if score > 0:
                candidates[field].append(
                    {
                        "index": index,
                        "source": header,
                        "score": score,
                        "method": method,
                    }
                )

    mapping: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for field in REQUIRED_COLUMNS:
        ranked = sorted(
            candidates[field], key=lambda candidate: (-candidate["score"], candidate["index"])
        )
        if not ranked:
            continue
        top = ranked[0]
        tied = [
            candidate
            for candidate in ranked[1:]
            if top["score"] - candidate["score"] <= AMBIGUITY_SCORE_DELTA
        ]
        if tied:
            names = sorted(
                {candidate["source"] for candidate in [top, *tied]},
                key=str.casefold,
            )
            if len(names) == 2:
                quoted = f"'{names[0]}' and '{names[1]}'"
                both = "both"
            else:
                quoted = ", ".join(f"'{name}'" for name in names)
                both = "all"
            problems.append(
                f"The columns {quoted} {both} look like {field}; "
                "rename or remove all but one."
            )
            continue
        mapping[field] = top

    by_index: dict[int, list[str]] = {}
    for field, match in mapping.items():
        by_index.setdefault(match["index"], []).append(field)
    for index, fields in by_index.items():
        if len(fields) > 1:
            problems.append(
                f"The column '{headers[index]}' could supply {', '.join(fields)}; "
                "rename the columns so each field has a distinct source."
            )
            for field in fields:
                mapping.pop(field, None)
    return mapping, problems


def _clean_cells(row: Any) -> list[str]:
    return ["" if value is None else str(value) for value in row]


def _trim_trailing_blanks(cells: list[str]) -> list[str]:
    trimmed = list(cells)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _select_header(
    rows: list[list[str]],
) -> tuple[int, list[str], dict[str, dict[str, Any]], list[str]]:
    """Find the most likely header row in the first rows of a table."""
    best: dict[str, Any] | None = None
    for index, row in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        cells = _trim_trailing_blanks(_clean_cells(row))
        if not cells or all(not cell.strip() for cell in cells):
            continue
        headers = [cell.strip() for cell in cells]
        mapping, problems = _collect_mapping(headers)
        quality = (
            len(mapping),
            sum(match["score"] for match in mapping.values()),
            -index,
        )
        if best is None or quality > best["quality"]:
            best = {
                "index": index,
                "headers": headers,
                "mapping": mapping,
                "problems": problems,
                "quality": quality,
            }
        if len(mapping) == len(REQUIRED_COLUMNS):
            return best["index"], best["headers"], best["mapping"], best["problems"]
    if best is None:
        return -1, [], {}, []
    return best["index"], best["headers"], best["mapping"], best["problems"]


def _looks_like_total_row(
    cells: list[str], mapping: dict[str, dict[str, Any]]
) -> bool:
    product_index = mapping["product"]["index"]
    if product_index >= len(cells):
        return False
    label = re.sub(r"[^a-z ]+", " ", cells[product_index].casefold())
    label = re.sub(r"\s+", " ", label).strip()
    if label not in _TOTAL_LABELS:
        return False
    numeric_indices = {
        mapping[field]["index"] for field in REQUIRED_COLUMNS if field != "product"
    }
    return any(
        cells[index].strip()
        for index in numeric_indices
        if index < len(cells)
    )


def _number_text(value: Any) -> str:
    """Clean currency, thousands separators, and unit text before Decimal parsing."""
    text = str(value).strip()
    if not text:
        return ""
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = re.sub(r"(?i)^(?:r|zar|usd|eur|gbp)\s*", "", text)
    text = re.sub(r"(?i)\s(?:r|zar|usd|eur|gbp)$", "", text)
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(?i)(?:each|ea|units?|pcs?)$", "", text)
    text = text.replace("%", "")
    if not text:
        return ""

    has_dot = "." in text
    has_comma = "," in text
    if has_dot and has_comma:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        parts = text.split(",")
        if len(parts) == 2 and parts[0] not in ("", "0", "-0"):
            if 1 <= len(parts[1]) <= 2:
                text = text.replace(",", ".")
            elif len(parts[1]) == 3 and re.fullmatch(r"\d{1,3}", parts[0].lstrip("-")):
                text = text.replace(",", "")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif has_dot and text.count(".") > 1:
        text = text.replace(".", "")

    return ("-" + text) if negative else text


def _validate_stock_values(
    frame: pd.DataFrame, row_numbers: list[int], source_name: str
) -> pd.DataFrame:
    frame = frame.copy()
    frame["product"] = frame["product"].map(
        lambda value: re.sub(r"\s+", " ", str(value)).strip()
    )
    if (frame["product"] == "").any():
        raise InventoryValidationError("Product names cannot be empty.")

    duplicate_mask = frame["product"].str.casefold().duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = sorted(set(frame.loc[duplicate_mask, "product"].tolist()))
        raise InventoryValidationError(
            "Product names must be unique (ignoring case and extra whitespace): "
            + ", ".join(duplicates)
            + "."
        )

    errors: list[str] = []
    for column in ("current_stock", "avg_daily_sales", "unit_cost", "lead_time_days"):
        converted: list[int | float | Decimal] = []
        for row_number, raw_value in zip(row_numbers, frame[column]):
            value = str(raw_value).strip()
            if not value:
                errors.append(f"Row {row_number}: {column} is required.")
                converted.append(0)
                continue
            cleaned = _number_text(value)
            try:
                number = Decimal(cleaned)
            except (InvalidOperation, ValueError):
                errors.append(f"Row {row_number}: {column} must be a number.")
                converted.append(0)
                continue
            if not number.is_finite():
                errors.append(f"Row {row_number}: {column} must be finite.")
                converted.append(0)
                continue
            try:
                as_float = float(number)
            except (OverflowError, ValueError):
                as_float = math.inf
            if not math.isfinite(as_float):
                errors.append(
                    f"Row {row_number}: {column} is outside the supported range."
                )
                converted.append(0)
                continue
            if number != 0 and as_float == 0:
                errors.append(
                    f"Row {row_number}: {column} is too small to represent safely."
                )
                converted.append(0)
                continue
            if number < 0:
                errors.append(f"Row {row_number}: {column} cannot be negative.")
                converted.append(0)
                continue
            if number > MAX_NUMERIC_VALUE:
                errors.append(
                    f"Row {row_number}: {column} is too large; "
                    f"the maximum supported value is {MAX_NUMERIC_VALUE:,.0f}."
                )
                converted.append(0)
                continue
            if column in ("current_stock", "lead_time_days"):
                if number != number.to_integral_value():
                    errors.append(f"Row {row_number}: {column} must be a whole number.")
                    converted.append(0)
                    continue
                converted.append(int(number))
            elif column == "unit_cost":
                converted.append(number)
            else:
                converted.append(float(number))
        frame[column] = converted

    if errors:
        raise InventoryValidationError(
            "Please correct the inventory data:\n- " + "\n- ".join(errors)
        )

    calculation_errors: list[str] = []
    for row_number, row in zip(
        row_numbers, frame.to_dict(orient="records")
    ):
        demand = row["avg_daily_sales"]
        stock = row["current_stock"]
        lead_time = row["lead_time_days"]
        try:
            coverage = stock / demand if demand > 0 else 0.0
        except OverflowError:
            coverage = math.inf
        if not math.isfinite(coverage):
            calculation_errors.append(
                f"Row {row_number}: current_stock and avg_daily_sales produce an "
                "unsupported coverage value."
            )
        if not math.isfinite(demand * lead_time):
            calculation_errors.append(
                f"Row {row_number}: avg_daily_sales and lead_time_days produce an "
                "unsupported lead-time demand."
            )
    if calculation_errors:
        raise InventoryValidationError(
            "Please correct the inventory data:\n- "
            + "\n- ".join(calculation_errors)
        )
    return frame.reset_index(drop=True)


def _looks_like_sales(tokens: set[str]) -> bool:
    return bool(tokens & {"sales", "sale", "demand", "sold", "usage"})


def _looks_like_lead_time(tokens: set[str]) -> bool:
    return (
        ("lead" in tokens and "time" in tokens)
        or "delivery" in tokens
        or "replenish" in tokens
        or "replenishment" in tokens
        or "day" in tokens
    )


def _looks_like_stock(tokens: set[str]) -> bool:
    return bool(tokens & {"stock", "quantity", "unit", "inventory", "hand"})


def _looks_like_cost(tokens: set[str]) -> bool:
    return bool(tokens & {"cost", "price"})


def _looks_like_money_total(tokens: set[str]) -> bool:
    return bool(tokens & {"value", "total", "amount", "extended", "cogs"})


def _missing_field_hints(headers: list[str], missing: list[str]) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for header in headers:
        normalised = _normalise_header(header)
        if not normalised:
            continue
        tokens = set(normalised.split())
        period = _period_hint(header)
        if (
            "avg_daily_sales" in missing
            and _looks_like_sales(tokens)
            and period not in (None, "day")
        ):
            if period == "period total":
                description = "a period total rather than a daily average"
            else:
                description = f"{period}ly sales"
            hint = (
                f"The column '{header}' looks like {description}. Convert it to "
                "average daily unit sales and rename it 'avg_daily_sales'."
            )
            if hint not in seen:
                hints.append(hint)
                seen.add(hint)
        if (
            "lead_time_days" in missing
            and _looks_like_lead_time(tokens)
            and period not in (None, "day")
        ):
            if period == "period total":
                description = "a period total rather than lead time in days"
            else:
                description = f"lead time in {period}s"
            hint = (
                f"The column '{header}' looks like {description}. Convert it to "
                "days and rename it 'lead_time_days'."
            )
            if hint not in seen:
                hints.append(hint)
                seen.add(hint)
        if (
            "current_stock" in missing
            and _looks_like_stock(tokens)
            and _looks_like_money_total(tokens)
        ):
            hint = (
                f"The column '{header}' is a monetary value, not a unit count. Add "
                "a column with units on hand and rename it 'current_stock'."
            )
            if hint not in seen:
                hints.append(hint)
                seen.add(hint)
        if (
            "unit_cost" in missing
            and _looks_like_cost(tokens)
            and _looks_like_money_total(tokens)
        ):
            hint = (
                f"The column '{header}' is a line total, not a per-unit cost. Add "
                "a column with the cost per unit and rename it 'unit_cost'."
            )
            if hint not in seen:
                hints.append(hint)
                seen.add(hint)
        if "unit_cost" in missing and tokens & {
            "selling",
            "retail",
            "rsp",
            "rrp",
        }:
            hint = (
                f"The column '{header}' is a selling price, not a supplier unit "
                "cost. Add a column with the cost per unit and rename it 'unit_cost'."
            )
            if hint not in seen:
                hints.append(hint)
                seen.add(hint)
    return hints


def _rejected_mapping_message(header: str, field: str) -> str | None:
    """Explain why a user-chosen column is still unsafe for a required field."""
    normalised = _normalise_header(header)
    tokens = set(normalised.split())
    period = _period_hint(header)
    if field == "avg_daily_sales" and period not in (None, "day"):
        if period == "period total":
            description = "a period total rather than a daily average"
        else:
            description = f"{period}ly sales"
        return (
            f"The column '{header}' looks like {description}. Convert it to average "
            "daily unit sales before choosing it for avg_daily_sales."
        )
    if field == "lead_time_days" and period not in (None, "day"):
        if period == "period total":
            description = "a period total rather than lead time in days"
        else:
            description = f"lead time in {period}s"
        return (
            f"The column '{header}' looks like {description}. Convert it to days "
            "before choosing it for lead_time_days."
        )
    if not tokens & _BLOCKED_TOKENS.get(field, set()):
        return None
    if (
        field == "current_stock"
        and _looks_like_stock(tokens)
        and _looks_like_money_total(tokens)
    ):
        return (
            f"The column '{header}' is a monetary value, not a unit count. Choose a "
            "column with units on hand for current_stock."
        )
    if (
        field == "unit_cost"
        and _looks_like_cost(tokens)
        and _looks_like_money_total(tokens)
    ):
        return (
            f"The column '{header}' is a line total, not a per-unit cost. Choose a "
            "column with the cost per unit for unit_cost."
        )
    if field == "unit_cost" and tokens & {"selling", "retail", "rsp", "rrp"}:
        return (
            f"The column '{header}' is a selling price, not a supplier unit cost. "
            "Choose a column with the cost per unit for unit_cost."
        )
    return (
        f"The column '{header}' cannot supply {field}. Choose a different column "
        "or rename the column."
    )


def _resolve_explicit_mapping(
    headers: list[str],
    column_mapping: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate a user-confirmed field-to-column mapping without guessing."""
    unknown = [key for key in column_mapping if key not in REQUIRED_COLUMNS]
    if unknown:
        raise InventoryValidationError(
            "Unknown inventory field(s): " + ", ".join(sorted(unknown)) + "."
        )

    exact = {header.strip(): index for index, header in enumerate(headers)}
    folded: dict[str, list[int]] = {}
    for index, header in enumerate(headers):
        folded.setdefault(header.strip().casefold(), []).append(index)

    resolved: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for field in REQUIRED_COLUMNS:
        value = column_mapping.get(field)
        if value is None or value == "":
            missing.append(field)
            continue
        index: int | None = None
        if isinstance(value, int) and not isinstance(value, bool):
            if 0 <= value < len(headers):
                index = value
        else:
            name = str(value).strip()
            if name in exact:
                index = exact[name]
            else:
                matches = folded.get(name.casefold(), [])
                if len(matches) == 1:
                    index = matches[0]
        if index is None:
            raise InventoryValidationError(
                f"The column '{value}' chosen for {field} was not found in the "
                "header row."
            )
        header = headers[index]
        if not header:
            raise InventoryValidationError(
                f"The column chosen for {field} has no heading. Add a heading to "
                "that column and try again."
            )
        unsafe = _rejected_mapping_message(header, field)
        if unsafe:
            raise InventoryValidationError(unsafe)
        score, _ = _score_header(header, field)
        resolved[field] = {
            "index": index,
            "source": header,
            "score": score,
            "method": "confirmed",
        }

    if missing:
        raise InventoryValidationError(
            "Choose a column for: " + ", ".join(missing) + "."
        )

    by_index: dict[int, list[str]] = {}
    for field, match in resolved.items():
        by_index.setdefault(match["index"], []).append(field)
    for index, fields in by_index.items():
        if len(fields) > 1:
            raise InventoryValidationError(
                f"The column '{headers[index]}' cannot supply {', '.join(fields)}; "
                "choose a different column for each field."
            )
    return resolved


def _build_validated_frame(
    rows: list[list[str]],
    source_name: str,
    file_type: str,
    sheet_name: str | None,
    forced_mapping: dict[str, Any] | None = None,
) -> pd.DataFrame:
    header_index, headers, mapping, problems = _select_header(rows)
    if header_index < 0:
        raise InventoryValidationError(f"The {source_name} has no header or data.")

    non_empty_headers = [header for header in headers if header]
    if len(non_empty_headers) != len(set(non_empty_headers)):
        raise InventoryValidationError(
            f"The {source_name} contains duplicate column names."
        )
    if forced_mapping is not None:
        mapping = _resolve_explicit_mapping(headers, forced_mapping)
        problems = []
    else:
        if problems:
            raise InventoryValidationError(
                "Please rename the ambiguous column(s) and upload again. "
                + " ".join(problems)
            )

        missing = [field for field in REQUIRED_COLUMNS if field not in mapping]
        if missing:
            hints = _missing_field_hints(headers, missing)
            if hints:
                raise InventoryValidationError(" ".join(hints))
            raise InventoryValidationError(
                "Missing required column(s): " + ", ".join(missing) + "."
            )

    data_rows: list[list[str]] = []
    row_numbers: list[int] = []
    skipped_total_rows: list[int] = []
    for offset in range(header_index + 1, len(rows)):
        cells = _trim_trailing_blanks(_clean_cells(rows[offset]))
        if not cells:
            continue
        if len(cells) > len(headers):
            raise InventoryValidationError(
                f"Row {offset + 1} has more values than the header row. Check for "
                "unquoted separators."
            )
        cells = cells + [""] * (len(headers) - len(cells))
        if all(not cell.strip() for cell in cells):
            continue
        if _looks_like_total_row(cells, mapping):
            skipped_total_rows.append(offset + 1)
            continue
        data_rows.append(cells)
        row_numbers.append(offset + 1)

    if not data_rows:
        raise InventoryValidationError(
            f"The {source_name} contains a header but no product rows."
        )
    if len(data_rows) > MAX_ROWS:
        raise InventoryValidationError(
            f"The {source_name} contains {len(data_rows)} rows; the limit is "
            f"{MAX_ROWS} products."
        )

    selected = pd.DataFrame(
        [
            [row[mapping[field]["index"]] for field in REQUIRED_COLUMNS]
            for row in data_rows
        ],
        columns=list(REQUIRED_COLUMNS),
    )
    validated = _validate_stock_values(selected, row_numbers, source_name)

    used_indices = {match["index"] for match in mapping.values()}
    validated.attrs.update(
        {
            "file_type": file_type,
            "sheet_name": sheet_name,
            "header_row": header_index + 1,
            "column_mapping": {
                field: mapping[field]["source"] for field in REQUIRED_COLUMNS
            },
            "mapping_details": {
                field: {
                    "source": mapping[field]["source"],
                    "score": mapping[field]["score"],
                    "method": mapping[field]["method"],
                }
                for field in REQUIRED_COLUMNS
            },
            "ignored_columns": [
                header
                for index, header in enumerate(headers)
                if index not in used_indices and header
            ],
            "skipped_total_rows": skipped_total_rows,
        }
    )
    return validated


def _inspect_rows(
    rows: list[list[str]],
    source_name: str,
    file_type: str,
    sheet_name: str | None,
    available_sheets: list[str] | None = None,
    encoding: str | None = None,
) -> dict[str, Any]:
    """Describe a table's headers, suggestions, problems, and preview rows."""
    header_index, headers, mapping, problems = _select_header(rows)
    if header_index < 0:
        raise InventoryValidationError(f"The {source_name} has no header or data.")

    non_empty_headers = [header for header in headers if header]
    if len(non_empty_headers) != len(set(non_empty_headers)):
        raise InventoryValidationError(
            f"The {source_name} contains duplicate column names."
        )

    candidates: dict[str, list[dict[str, Any]]] = {
        field: [] for field in REQUIRED_COLUMNS
    }
    for index, header in enumerate(headers):
        for field in REQUIRED_COLUMNS:
            score, method = _score_header(header, field)
            if score > 0:
                candidates[field].append(
                    {
                        "index": index,
                        "source": header,
                        "score": score,
                        "method": method,
                    }
                )
    for field in candidates:
        candidates[field] = sorted(
            candidates[field],
            key=lambda candidate: (-candidate["score"], candidate["index"]),
        )[:6]

    sample_rows: list[list[str]] = []
    for offset in range(header_index + 1, len(rows)):
        cells = _trim_trailing_blanks(_clean_cells(rows[offset]))
        if not cells or all(not cell.strip() for cell in cells):
            continue
        padded = cells + [""] * (len(headers) - len(cells))
        sample_rows.append([cell[:120] for cell in padded[: len(headers)]])
        if len(sample_rows) == 4:
            break

    used_indices = {match["index"] for match in mapping.values()}
    missing = [field for field in REQUIRED_COLUMNS if field not in mapping]
    return {
        "source_name": source_name,
        "file_type": file_type,
        "sheet_name": sheet_name,
        "available_sheets": list(available_sheets or []),
        "header_row": header_index + 1,
        "headers": headers,
        "suggested_mapping": {
            field: mapping[field]["index"] for field in REQUIRED_COLUMNS if field in mapping
        },
        "candidates": candidates,
        "missing_fields": missing,
        "problems": problems,
        "ignored_columns": [
            header
            for index, header in enumerate(headers)
            if index not in used_indices and header
        ],
        "sample_rows": sample_rows,
        "is_ready": not problems and not missing,
        "encoding": encoding,
    }


def _decode_csv(file_data: bytes) -> tuple[str, str]:
    if file_data.startswith(b"\xef\xbb\xbf"):
        return file_data.decode("utf-8-sig"), "utf-8-sig"
    if file_data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return file_data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8", "cp1252"):
        try:
            return file_data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return file_data.decode("latin-1"), "latin-1"


def _read_csv_rows(text: str) -> list[list[str]]:
    best: dict[str, Any] | None = None
    for delimiter in (",", ";", "\t", "|"):
        try:
            rows = list(
                csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
            )
        except csv.Error:
            continue
        _, headers, mapping, _ = _select_header(rows)
        quality = (
            len(mapping),
            sum(match["score"] for match in mapping.values()),
            len(headers),
        )
        if best is None or quality > best["quality"]:
            best = {"rows": rows, "quality": quality}
    if best is None:
        raise InventoryValidationError(
            "The file could not be read as a well-formed UTF-8 CSV."
        )
    return best["rows"]


def _detect_file_type(file_data: bytes, filename: str | None) -> str:
    suffix = Path(filename).suffix.casefold() if filename else ""
    if file_data[:4] == b"PK\x03\x04":
        return "xlsx"
    if file_data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    if suffix in (".xlsx", ".xls"):
        return suffix[1:]
    if suffix and suffix != ".csv":
        raise InventoryValidationError(
            "Unsupported file type. Upload a .csv, .xlsx, or .xls file."
        )
    return "csv"


def _prepare_file(
    file_data: bytes | str, filename: str | None
) -> tuple[bytes, str]:
    if isinstance(file_data, str):
        file_data = file_data.encode("utf-8")
    file_type = _detect_file_type(file_data, filename)
    label = "CSV file" if file_type == "csv" else "workbook"
    if not file_data:
        raise InventoryValidationError(f"The {label} is empty.")
    if len(file_data) > MAX_FILE_BYTES:
        raise InventoryValidationError(
            f"The {label} exceeds the 5 MB size limit."
        )
    return file_data, file_type


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    return str(value).strip()


def _workbook_sheet_names(file_data: bytes, file_type: str) -> list[str]:
    if file_type == "xlsx":
        try:
            import openpyxl

            workbook = openpyxl.load_workbook(
                io.BytesIO(file_data), read_only=True, data_only=True
            )
        except Exception as exc:  # noqa: BLE001 - openpyxl raises several types
            logging.exception("Could not read the uploaded Excel workbook")
            raise InventoryValidationError(
                "The workbook could not be read. Check that it is a valid Excel "
                "file and is not password protected."
            ) from exc
        try:
            return list(workbook.sheetnames)
        finally:
            try:
                workbook.close()
            except Exception:  # noqa: BLE001 - closing must never mask an error
                pass
    try:
        import xlrd

        workbook = xlrd.open_workbook(file_contents=file_data)
        return list(workbook.sheet_names())
    except Exception as exc:  # noqa: BLE001 - xlrd raises several types
        raise InventoryValidationError(
            "The workbook could not be read. Check that it is a valid Excel "
            "file and is not password protected."
        ) from exc


def _workbook_rows(
    file_data: bytes, file_type: str, sheet_name: str
) -> list[list[str]]:
    names = _workbook_sheet_names(file_data, file_type)
    if sheet_name not in names:
        raise InventoryValidationError(
            f"The worksheet '{sheet_name}' was not found. Available worksheets: "
            + ", ".join(names)
            + "."
        )
    if file_type == "xlsx":
        try:
            import openpyxl

            workbook = openpyxl.load_workbook(
                io.BytesIO(file_data), read_only=True, data_only=True
            )
        except Exception as exc:  # noqa: BLE001
            raise InventoryValidationError(
                "The workbook could not be read. Check that it is a valid Excel "
                "file and is not password protected."
            ) from exc
        try:
            worksheet = workbook[sheet_name]
            return [
                [_cell_to_text(value) for value in row]
                for row in worksheet.iter_rows(values_only=True)
            ]
        finally:
            try:
                workbook.close()
            except Exception:  # noqa: BLE001
                pass
    try:
        import xlrd

        workbook = xlrd.open_workbook(file_contents=file_data)
        worksheet = workbook.sheet_by_name(sheet_name)
        return [
            [_cell_to_text(worksheet.cell_value(row, column)) for column in range(worksheet.ncols)]
            for row in range(worksheet.nrows)
        ]
    except Exception as exc:  # noqa: BLE001
        raise InventoryValidationError(
            "The workbook could not be read. Check that it is a valid Excel "
            "file and is not password protected."
        ) from exc


def _sheet_scores(
    file_data: bytes, file_type: str, names: list[str]
) -> list[tuple[int, str]]:
    scores: list[tuple[int, str]] = []
    for name in names:
        rows = _workbook_rows(file_data, file_type, name)
        _, _, mapping, _ = _select_header(rows)
        scores.append((len(mapping), name))
    return scores


def _best_sheet(
    file_data: bytes,
    file_type: str,
    names: list[str],
    *,
    require_unique: bool,
) -> str | None:
    scores = _sheet_scores(file_data, file_type, names)
    full = [name for count, name in scores if count == len(REQUIRED_COLUMNS)]
    if len(full) == 1:
        return full[0]
    if len(full) > 1:
        if require_unique:
            raise InventoryValidationError(
                "The workbook contains multiple worksheets that look like "
                "inventory: " + ", ".join(f"'{name}'" for name in full) + ". "
                "Choose the worksheet to use and try again."
            )
        return None
    if not scores:
        return None
    best_count = max(count for count, _ in scores)
    for count, name in scores:
        if count == best_count:
            return name
    return names[0]


def _validate_workbook(
    file_data: bytes,
    file_type: str,
    sheet_name: str | None,
    column_mapping: dict[str, Any] | None = None,
) -> pd.DataFrame:
    names = _workbook_sheet_names(file_data, file_type)
    if not names:
        raise InventoryValidationError("The workbook contains no worksheets.")
    if sheet_name is not None and sheet_name not in names:
        raise InventoryValidationError(
            f"The worksheet '{sheet_name}' was not found. Available worksheets: "
            + ", ".join(names)
            + "."
        )
    chosen = sheet_name if sheet_name is not None else _best_sheet(
        file_data, file_type, names, require_unique=True
    )
    if chosen is None:
        chosen = names[0]
    rows = _workbook_rows(file_data, file_type, chosen)
    return _build_validated_frame(
        rows,
        f"worksheet '{chosen}'",
        file_type,
        chosen,
        forced_mapping=column_mapping,
    )


def _validate_csv(
    file_data: bytes, column_mapping: dict[str, Any] | None = None
) -> pd.DataFrame:
    text, encoding = _decode_csv(file_data)
    if not text.strip():
        raise InventoryValidationError("The CSV file has no header or data.")
    rows = _read_csv_rows(text)
    frame = _build_validated_frame(
        rows, "CSV", "csv", None, forced_mapping=column_mapping
    )
    frame.attrs["encoding"] = encoding
    return frame


def validate_inventory_file(
    file_data: bytes | str,
    filename: str | None = None,
    sheet_name: str | None = None,
    column_mapping: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Parse a CSV or Excel workbook and map arbitrary headers to the schema.

    Pass ``column_mapping`` with a header name or column index for each required
    field to apply a user-confirmed mapping instead of the deterministic guess.
    """
    prepared, file_type = _prepare_file(file_data, filename)
    if file_type == "csv":
        return _validate_csv(prepared, column_mapping)
    return _validate_workbook(prepared, file_type, sheet_name, column_mapping)


def inspect_inventory_file(
    file_data: bytes | str,
    filename: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Return headers, mapping suggestions, and preview rows without validating data.

    The report lets the interface show a mapping-confirmation step when the
    deterministic mapper is ambiguous or incomplete.
    """
    prepared, file_type = _prepare_file(file_data, filename)
    if file_type == "csv":
        text, encoding = _decode_csv(prepared)
        if not text.strip():
            raise InventoryValidationError("The CSV file has no header or data.")
        rows = _read_csv_rows(text)
        return _inspect_rows(rows, "CSV", "csv", None, encoding=encoding)

    names = _workbook_sheet_names(prepared, file_type)
    if not names:
        raise InventoryValidationError("The workbook contains no worksheets.")
    if sheet_name is not None and sheet_name not in names:
        raise InventoryValidationError(
            f"The worksheet '{sheet_name}' was not found. Available worksheets: "
            + ", ".join(names)
            + "."
        )
    chosen = (
        sheet_name
        if sheet_name is not None
        else _best_sheet(prepared, file_type, names, require_unique=False)
    )
    if chosen is None:
        chosen = names[0]
    rows = _workbook_rows(prepared, file_type, chosen)
    return _inspect_rows(
        rows,
        f"worksheet '{chosen}'",
        file_type,
        chosen,
        available_sheets=names,
    )


def validate_inventory_csv(file_data: bytes | str) -> pd.DataFrame:
    """Backward-compatible CSV entry point used by tests and the sample loader."""
    return validate_inventory_file(file_data, filename="inventory.csv")


def list_workbook_sheets(
    file_data: bytes | str, filename: str | None = None
) -> list[str]:
    """Return worksheet names for an Excel file; return an empty list for CSV."""
    prepared, file_type = _prepare_file(file_data, filename)
    if file_type == "csv":
        return []
    return _workbook_sheet_names(prepared, file_type)


def suggest_inventory_sheet(
    file_data: bytes | str, filename: str | None = None
) -> str | None:
    """Return the only sheet that fully maps to the schema, when there is one."""
    prepared, file_type = _prepare_file(file_data, filename)
    if file_type == "csv":
        return None
    names = _workbook_sheet_names(prepared, file_type)
    if not names:
        return None
    return _best_sheet(prepared, file_type, names, require_unique=False)


def analyze_inventory(
    inventory: pd.DataFrame, uploaded_at: str | None = None
) -> dict[str, Any]:
    """Calculate all inventory metrics and return ranked product rows and a summary."""
    products: list[dict[str, Any]] = []
    for row in inventory.to_dict(orient="records"):
        stock = int(row["current_stock"])
        demand = float(row["avg_daily_sales"])
        unit_cost = Decimal(str(row["unit_cost"]))
        lead_time = int(row["lead_time_days"])
        lead_time_demand = demand * lead_time
        reorder_point = lead_time_demand
        coverage = stock / demand if demand > 0 else None
        coverage_gap = coverage - lead_time if coverage is not None else None

        if stock == 0 and demand > 0:
            status = "OUT OF STOCK"
            priority_rank = 0
        elif demand == 0:
            status = "NO RECORDED DEMAND"
            priority_rank = 4
        elif coverage is not None and coverage < lead_time - COMPARISON_TOLERANCE:
            status = "SHORTAGE RISK"
            priority_rank = 1
        elif coverage is not None and math.isclose(
            coverage, lead_time, rel_tol=0.0, abs_tol=COMPARISON_TOLERANCE
        ):
            status = "REORDER NOW"
            priority_rank = 2
        else:
            status = "HEALTHY"
            priority_rank = 3

        try:
            with localcontext() as context:
                context.prec = 50
                product_value = (unit_cost * stock).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
        except InvalidOperation as exc:
            raise InventoryValidationError(
                f"Inventory value for '{row['product']}' is too large to represent."
            ) from exc
        products.append(
            {
                "product": row["product"],
                "current_stock": stock,
                "avg_daily_sales": demand,
                "unit_cost": unit_cost,
                "lead_time_days": lead_time,
                "inventory_value": product_value,
                "stock_coverage_days": coverage,
                "lead_time_demand": lead_time_demand,
                "reorder_point": reorder_point,
                "coverage_gap_days": coverage_gap,
                "status": status,
                "_priority_rank": priority_rank,
            }
        )

    products.sort(
        key=lambda product: (
            product["_priority_rank"],
            product["coverage_gap_days"]
            if product["status"] == "SHORTAGE RISK"
            else 0,
            product["product"].casefold(),
        )
    )
    public_products = [
        {key: value for key, value in product.items() if not key.startswith("_")}
        for product in products
    ]
    attention = [
        product
        for product in public_products
        if product["status"] in ("OUT OF STOCK", "SHORTAGE RISK", "REORDER NOW")
    ]
    try:
        with localcontext() as context:
            context.prec = 50
            total_value = sum(
                (product["inventory_value"] for product in public_products),
                start=Decimal("0"),
            ).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise InventoryValidationError(
            "The total inventory value is too large to represent."
        ) from exc
    coverage_values = [
        product["stock_coverage_days"]
        for product in public_products
        if product["stock_coverage_days"] is not None
    ]

    return {
        "products": public_products,
        "summary": {
            "total_products": len(public_products),
            "total_stock_units": sum(
                product["current_stock"] for product in public_products
            ),
            "total_inventory_value": total_value,
            "average_stock_coverage_days": (
                sum(coverage_values) / len(coverage_values)
                if coverage_values
                else None
            ),
            "out_of_stock_count": sum(
                product["status"] == "OUT OF STOCK" for product in public_products
            ),
            "shortage_risk_count": sum(
                product["status"] == "SHORTAGE RISK" for product in public_products
            ),
            "reorder_now_count": sum(
                product["status"] == "REORDER NOW" for product in public_products
            ),
            "attention_products": attention,
            "uploaded_at": uploaded_at,
        },
    }


def get_product_details(
    analysis: dict[str, Any], product_name: str
) -> dict[str, Any]:
    """Find a product without guessing; return a structured not-found result."""
    if not isinstance(product_name, str) or not product_name.strip():
        return {
            "found": False,
            "product_name": product_name,
            "error": "A product name is required.",
        }
    wanted = re.sub(r"\s+", " ", product_name).strip().casefold()
    for product in analysis["products"]:
        if product["product"].casefold() == wanted:
            return {"found": True, **product}
    return {
        "found": False,
        "product_name": product_name,
        "error": "This product is not present in the active inventory.",
    }


def get_priority_products(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all items needing attention in deterministic urgency order."""
    return list(analysis["summary"]["attention_products"])
