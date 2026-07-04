"""
validator.py
Step 3: Self-validation — ask Gemini to verify that the scenario
is unambiguous (only one plausible tax intent).
Retries up to MAX_RETRIES times if the scenario is deemed ambiguous.
"""
import json
from modules.llm_client import LLMClient
from modules.scenario_builder import ScenarioBuilder
from prompts.prompts import SELF_VALIDATE_PROMPT

MAX_RETRIES = 3


class Validator:
    def __init__(self, client: LLMClient, builder: ScenarioBuilder):
        self.client = client
        self.builder = builder

    def validate_and_retry(self, chapter: dict, pdf_file) -> dict | None:
        """
        Try to generate a valid, unambiguous scenario for a chapter.
        Returns the scenario dict if validation passes, or None if all retries fail.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"[Validator] Attempt {attempt}/{MAX_RETRIES} for chapter: {chapter.get('title')}")
            try:
                scenario = self.builder.build_scenario(chapter, pdf_file)
            except ValueError as e:
                print(f"[Validator] Scenario generation failed: {e}")
                continue

            # Build combined form list for validation
            all_forms = scenario.get("mandatory_forms", []) + scenario.get("supporting_forms", [])
            forms_summary = [{"form": f["form"], "content": f["content"]} for f in all_forms]
            forms_json_str = json.dumps(forms_summary, indent=2)

            prompt = SELF_VALIDATE_PROMPT.format(forms_json=forms_json_str)

            try:
                validation = self.client.generate_json(prompt)
            except ValueError as e:
                print(f"[Validator] Validation parse error: {e}")
                continue

            if validation.get("is_unique") is True:
                print(f"[Validator] ✅ Scenario validated. Intent: {validation.get('inferred_intent')}")
                scenario["_validated_intent"] = validation.get("inferred_intent")
                scenario["_key_signals"] = validation.get("key_signals", [])
                return scenario
            else:
                print(f"[Validator] ❌ Ambiguous scenario: {validation.get('ambiguity_reason')} — retrying...")

        print(f"[Validator] ⚠️  All {MAX_RETRIES} attempts failed for chapter '{chapter.get('title')}'. Skipping.")
        return None
