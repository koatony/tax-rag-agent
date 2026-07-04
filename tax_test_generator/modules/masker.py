"""
masker.py
Step 4: Pure code logic — no LLM needed.
Removes ONE mandatory form from a validated scenario to create
the test input and ground truth answer pair.
"""
import copy
import random


class Masker:
    def apply(self, scenario: dict) -> dict:
        """
        Given a validated scenario dict, randomly pick one mandatory form to remove.
        Returns a dict with two keys:
          - test_case:  the input to feed the RAG system (only remaining forms)
          - ground_truth: the complete answer, including what was removed and why
        """
        mandatory_forms = scenario.get("mandatory_forms", [])
        supporting_forms = scenario.get("supporting_forms", [])

        if not mandatory_forms:
            raise ValueError("Cannot mask: scenario has no mandatory_forms.")

        # Pick one mandatory form to mask
        mask_index = random.randint(0, len(mandatory_forms) - 1)
        removed_form = mandatory_forms[mask_index]
        remaining_mandatory = [f for i, f in enumerate(mandatory_forms) if i != mask_index]

        # Test input: remaining mandatory + all supporting (but NOT the removed form)
        test_input_forms = remaining_mandatory + supporting_forms

        test_case = {
            "id": scenario.get("scenario_id", "unknown"),
            "uploaded_forms": [
                {"form": f["form"], "content": f["content"]}
                for f in test_input_forms
            ]
        }

        ground_truth = {
            "id": scenario.get("scenario_id", "unknown"),
            "inferred_intent": scenario.get("_validated_intent", ""),
            "key_signals": scenario.get("_key_signals", []),
            "missing_form": {
                "form": removed_form["form"],
                "content": removed_form["content"],
                "legal_basis": removed_form.get("legal_basis", "")
            },
            "complete_mandatory_forms": mandatory_forms,
            "complete_supporting_forms": supporting_forms,
            "taxpayer_profile": scenario.get("taxpayer_profile", {}),
            "chapter_ref": scenario.get("chapter_ref", "")
        }

        return {"test_case": test_case, "ground_truth": ground_truth}
