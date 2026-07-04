"""
scenario_builder.py
Step 2: Generate a complete tax scenario (all forms, all fields filled)
for a given chapter.
"""
import json
from modules.llm_client import LLMClient
from prompts.prompts import SCENARIO_GEN_PROMPT


class ScenarioBuilder:
    def __init__(self, client: LLMClient):
        self.client = client

    def build_scenario(self, chapter: dict, pdf_file) -> dict:
        """
        For a given chapter dict, generate one complete tax scenario.
        Returns the parsed scenario dict.
        """
        prompt = SCENARIO_GEN_PROMPT.format(
            chapter_title=chapter.get("title", ""),
            chapter_topic=chapter.get("topic_summary", ""),
            chapter_id=chapter.get("chapter_id", ""),
        )

        print(f"[ScenarioBuilder] Generating scenario for chapter: {chapter.get('title')}")
        scenario = self.client.generate_json(prompt, pdf_file)

        # Basic validation: must have mandatory_forms
        if not isinstance(scenario.get("mandatory_forms"), list):
            raise ValueError(f"Scenario missing mandatory_forms list: {scenario}")
        if len(scenario["mandatory_forms"]) == 0:
            raise ValueError("Scenario has no mandatory_forms — cannot mask later.")

        # Validate all form fields are non-empty
        self._validate_fields(scenario)

        return scenario

    def _validate_fields(self, scenario: dict):
        """Ensure no form fields are None or empty string."""
        all_forms = scenario.get("mandatory_forms", []) + scenario.get("supporting_forms", [])
        for form in all_forms:
            for field_key, field_val in form.get("content", {}).items():
                if field_val is None or field_val == "":
                    raise ValueError(
                        f"Form '{form.get('form')}' has empty field '{field_key}'. "
                        "All fields must have concrete values."
                    )
