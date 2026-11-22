"""Opt-in live Gemini test; run only when explicitly requested."""

import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from gemini_agent import _client_from_environment, answer_inventory_question
from inventory_engine import analyze_inventory, validate_inventory_csv

pytestmark = pytest.mark.skipif(
    os.getenv("FULLSHELF_RUN_LIVE_GEMINI") != "1",
    reason="Set FULLSHELF_RUN_LIVE_GEMINI=1 to make a live Gemini API request.",
)


def test_live_gemini_calls_product_tool_and_uses_its_result():
    client, model = _client_from_environment()
    called_tools = []

    class TracingModels:
        def generate_content(self, **kwargs):
            response = client.models.generate_content(**kwargs)
            for candidate in getattr(response, "candidates", []) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", []) or []:
                    function_call = getattr(part, "function_call", None)
                    if function_call is not None:
                        called_tools.append(function_call.name)
            return response

    inventory_path = Path(__file__).parents[1] / "data" / "sample_inventory.csv"
    analysis = analyze_inventory(validate_inventory_csv(inventory_path.read_bytes()))
    answer = answer_inventory_question(
        "Use the product details tool. How many Lip Gloss units are in stock? "
        "Answer with the exact stock count from the tool.",
        analysis,
        client=SimpleNamespace(models=TracingModels()),
        model=model,
    )

    assert "get_product_details" in called_tools
    assert re.search(r"\b6\b", answer), answer
