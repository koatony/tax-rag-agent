CHAPTER_INDEX_PROMPT = """
You are a tax law expert analyzing an IRS publication PDF.

Your task is to extract the chapter structure of this document.
For each chapter or major section, provide:
1. Chapter number or name
2. A brief topic summary (1-2 sentences)
3. The target taxpayer profile this chapter applies to

Return ONLY a valid JSON array in this exact format, with no extra explanation:
[
  {
    "chapter_id": "ch01",
    "title": "Chapter title here",
    "topic_summary": "Brief description of what this chapter covers",
    "target_taxpayer": "Who this chapter applies to (e.g., 'employees with wage income', 'self-employed individuals')"
  }
]
"""

SCENARIO_GEN_PROMPT = """
You are a tax law expert. You have access to an IRS publication PDF.

Your task is to create ONE realistic tax scenario based specifically on Chapter: {chapter_title}
Topic: {chapter_topic}

CRITICAL REQUIREMENTS:
1. Create a realistic virtual taxpayer (fictional name, fictional numbers)
2. Generate a COMPLETE set of all IRS forms this taxpayer would have or need
3. Every single form field MUST have a concrete value (number, string, date) — NO empty fields, NO null, NO "N/A" unless it is a legally valid empty field for that specific form
4. Include a STRONG SIGNAL TRIGGER: The numbers must make the tax situation UNAMBIGUOUS. For example, if the scenario is about estimated tax, ensure the income and withholding gap is large enough that there is ONLY ONE logical conclusion
5. Clearly separate mandatory forms (legally required) from supporting forms (informational)
6. Cite the exact text from the PDF that makes each mandatory form required

Return ONLY a valid JSON object in this exact format:
{{
  "scenario_id": "unique_id_here",
  "chapter_ref": "{chapter_id}",
  "taxpayer_profile": {{
    "name": "Fictional name",
    "filing_status": "Single/MFJ/MFS/HoH/QSS",
    "occupation": "Description",
    "scenario_summary": "One sentence describing what tax situation this person is in"
  }},
  "mandatory_forms": [
    {{
      "form": "Form name (e.g., Form 1040-ES)",
      "content": {{
        "field_name_1": "value1",
        "field_name_2": "value2"
      }},
      "legal_basis": "Exact quoted text from the PDF that mandates this form"
    }}
  ],
  "supporting_forms": [
    {{
      "form": "Form name",
      "content": {{
        "field_name_1": "value1"
      }}
    }}
  ]
}}
"""

SELF_VALIDATE_PROMPT = """
You are a tax expert acting as a test case reviewer.

Below is a set of tax forms (as JSON) submitted by a taxpayer:
{forms_json}

Question: Based ONLY on the data in these forms (numbers, amounts, types of income, filing status, etc.), can you determine with HIGH CONFIDENCE (>90%) what the taxpayer's primary tax filing need or problem is?

Answer requirements:
- If YES: state the single most likely tax filing need in one sentence, and explain which specific data points make it unambiguous
- If NO: explain what is ambiguous or what additional signals would be needed

Return ONLY a valid JSON object:
{{
  "is_unique": true or false,
  "inferred_intent": "The single tax filing need (or 'AMBIGUOUS' if not unique)",
  "key_signals": ["data point 1 that reveals intent", "data point 2"],
  "ambiguity_reason": "Only fill this if is_unique is false — explain what is ambiguous"
}}
"""
