import json

import pytest

from gemini_agent import AgentError, suggest_column_mapping

HEADERS = [
    "Part No",
    "Units On Hand",
    "Sold per Day",
    "Supplier Cost",
    "Wait Days",
    "Category",
]


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeModels:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return FakeResponse(self.text)


class FakeClient:
    def __init__(self, text: str):
        self.models = FakeModels(text)


def _json(mappings):
    return json.dumps({"mappings": mappings})


def test_suggestions_are_limited_to_supplied_headers():
    client = FakeClient(
        _json(
            [
                {"field": "product", "column": "Part No", "confidence": 0.9},
                {"field": "current_stock", "column": "Units On Hand", "confidence": 0.95},
                {"field": "avg_daily_sales", "column": "Sold per Day", "confidence": 0.9},
                {"field": "unit_cost", "column": "Supplier Cost", "confidence": 0.9},
                {"field": "lead_time_days", "column": "Wait Days", "confidence": 0.8},
            ]
        )
    )

    result = suggest_column_mapping(
        HEADERS, [["A-1", "8", "1.5", "72.5", "4", "Skincare"]], client=client, model="test"
    )

    assert result == {
        "product": {"column": "Part No", "confidence": 0.9, "method": "gemini"},
        "current_stock": {
            "column": "Units On Hand",
            "confidence": 0.95,
            "method": "gemini",
        },
        "avg_daily_sales": {
            "column": "Sold per Day",
            "confidence": 0.9,
            "method": "gemini",
        },
        "unit_cost": {"column": "Supplier Cost", "confidence": 0.9, "method": "gemini"},
        "lead_time_days": {"column": "Wait Days", "confidence": 0.8, "method": "gemini"},
    }


def test_hallucinated_columns_and_unknown_fields_are_dropped():
    client = FakeClient(
        _json(
            [
                {"field": "product", "column": "Part No", "confidence": 0.9},
                {"field": "current_stock", "column": "Imaginary Stock", "confidence": 0.9},
                {"field": "profit_margin", "column": "Supplier Cost", "confidence": 0.9},
            ]
        )
    )

    result = suggest_column_mapping(HEADERS, [], client=client, model="test")

    assert result == {
        "product": {"column": "Part No", "confidence": 0.9, "method": "gemini"}
    }


def test_only_three_sample_rows_are_sent_and_cells_are_truncated():
    client = FakeClient(_json([]))
    rows = [
        ["A-1", "8", "1.5", "72.5", "4", "Skincare"],
        ["A-2", "6", "2", "28", "3", "Makeup"],
        ["A-3", "3", "1", "95", "5", "Skincare"],
        ["SECRET", "9", "9", "9", "9", "Hidden"],
    ]

    suggest_column_mapping(HEADERS, rows, client=client, model="test")

    sent = json.loads(client.models.calls[0]["contents"][0].parts[0].text)
    assert len(sent["sample_rows"]) == 3
    assert sent["sample_rows"][0][0] == "A-1"
    assert "SECRET" not in json.dumps(sent)


def test_duplicate_column_keeps_the_higher_confidence_field():
    client = FakeClient(
        _json(
            [
                {"field": "product", "column": "Supplier Cost", "confidence": 0.8},
                {"field": "unit_cost", "column": "Supplier Cost", "confidence": 0.9},
            ]
        )
    )

    result = suggest_column_mapping(HEADERS, [], client=client, model="test")

    assert result == {
        "unit_cost": {"column": "Supplier Cost", "confidence": 0.9, "method": "gemini"}
    }


def test_column_matching_is_case_insensitive():
    client = FakeClient(
        _json([{"field": "current_stock", "column": "units on hand", "confidence": 0.9}])
    )

    result = suggest_column_mapping(HEADERS, [], client=client, model="test")

    assert result["current_stock"]["column"] == "Units On Hand"


def test_invalid_response_raises_a_safe_error():
    client = FakeClient("I could not find any columns.")

    with pytest.raises(AgentError, match="could not be read"):
        suggest_column_mapping(HEADERS, [], client=client, model="test")


def test_empty_headers_are_rejected_before_calling_the_model():
    client = FakeClient(_json([]))

    with pytest.raises(AgentError, match="no column headings"):
        suggest_column_mapping([], [], client=client, model="test")

    assert client.models.calls == []
