import json
from types import SimpleNamespace

import pytest

from gemini_agent import (
    _api_error_message,
    _content_from_history,
    answer_inventory_question,
    build_inventory_tools,
)
from inventory_engine import analyze_inventory, validate_inventory_csv


def test_inventory_tools_use_the_bound_active_dataset():
    inventory = validate_inventory_csv(
        b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nLip Gloss,4,2,25,3\n"
    )
    analysis = analyze_inventory(inventory, "2026-11-07T18:00:00+02:00")
    tools = build_inventory_tools(analysis)

    assert tools["get_inventory_summary"]()["total_products"] == 1
    assert tools["get_product_details"]("Lip Gloss")["current_stock"] == 4
    assert tools["get_priority_products"]()[0]["product"] == "Lip Gloss"


def test_model_receives_actual_tool_result_before_final_text():
    observed_tool_reply = []

    def function_part():
        return SimpleNamespace(
            function_call=SimpleNamespace(
                name="get_product_details", args={"product_name": "Lip Gloss"}
            )
        )

    class FakeModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            contents = kwargs["contents"]
            if self.calls == 1:
                return SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(parts=[function_part()])
                        )
                    ],
                    text=None,
                )
            tool_content = contents[-1]
            observed_tool_reply.append(
                tool_content.parts[0].function_response.response
            )
            return SimpleNamespace(candidates=[], text="You have 4 units of Lip Gloss.")

    client = SimpleNamespace(models=FakeModels())
    inventory = validate_inventory_csv(
        b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nLip Gloss,4,2,25,3\n"
    )

    answer = answer_inventory_question(
        "How many lip glosses are left?",
        analyze_inventory(inventory),
        client=client,
        model="test-model",
    )
    assert answer == "You have 4 units of Lip Gloss."
    assert observed_tool_reply[0]["result"]["current_stock"] == 4


def test_tool_output_is_json_safe():
    inventory = validate_inventory_csv(
        b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nLip Gloss,4,2,25,3\n"
    )
    tools = build_inventory_tools(analyze_inventory(inventory))

    summary = tools["get_inventory_summary"]()
    details = tools["get_product_details"]("Lip Gloss")

    assert isinstance(summary["total_inventory_value"], float)
    assert isinstance(details["unit_cost"], float)
    assert isinstance(details["inventory_value"], float)
    json.dumps(summary)
    json.dumps(details)


def test_parallel_tool_calls_use_one_user_turn():
    observed_contents = []

    def call_part(name, args):
        return SimpleNamespace(
            function_call=SimpleNamespace(name=name, args=args, id=f"call-{name}")
        )

    class FakeModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(
                                role="model",
                                parts=[
                                    call_part(
                                        "get_product_details",
                                        {"product_name": "Lip Gloss"},
                                    ),
                                    call_part("get_priority_products", {}),
                                ]
                            )
                        )
                    ],
                    text=None,
                )
            observed_contents.append(list(kwargs["contents"]))
            return SimpleNamespace(candidates=[], text="Both results are above.")

    inventory = validate_inventory_csv(
        b"product,current_stock,avg_daily_sales,unit_cost,lead_time_days\nLip Gloss,4,2,25,3\n"
    )
    answer = answer_inventory_question(
        "Check Lip Gloss and the priority list.",
        analyze_inventory(inventory),
        client=SimpleNamespace(models=FakeModels()),
        model="test-model",
    )

    assert answer == "Both results are above."
    sent = observed_contents[0]
    assert [content.role for content in sent] == ["user", "model", "user"]
    tool_turn = sent[-1]
    assert [part.function_response.name for part in tool_turn.parts] == [
        "get_product_details",
        "get_priority_products",
    ]
    assert [part.function_response.id for part in tool_turn.parts] == [
        "call-get_product_details",
        "call-get_priority_products",
    ]


def test_history_starts_with_a_user_turn_and_skips_ui_errors():
    history = [
        {"role": "assistant", "content": "Welcome"},
        {"role": "user", "content": "How many?"},
        {"role": "assistant", "content": "AI assistant unavailable: timeout"},
        {"role": "assistant", "content": "You have 4 units."},
    ]

    contents = _content_from_history(history)

    assert [content.role for content in contents] == ["user", "model"]
    assert contents[1].parts[0].text == "You have 4 units."


@pytest.mark.parametrize(
    "code, expected",
    [
        (401, "authenticate"),
        (403, "authenticate"),
        (404, "not available"),
        (429, "rate-limited"),
        (503, "temporarily unavailable"),
    ],
)
def test_api_errors_are_translated_to_actionable_messages(code, expected):
    assert expected in _api_error_message(SimpleNamespace(code=code))
