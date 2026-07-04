"""
main.py
Entry point for the Tax Diagnostic Test Set Generator.

Usage:
  python main.py --pdf raw_docs/pub505.pdf --max-per-chapter 5 --output output/
"""
import argparse
import json
import os
from pathlib import Path

from modules.llm_client import LLMClient
from modules.chapter_indexer import ChapterIndexer
from modules.scenario_builder import ScenarioBuilder
from modules.validator import Validator
from modules.masker import Masker


def parse_args():
    parser = argparse.ArgumentParser(description="Tax Diagnostic Test Set Generator")
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to the IRS publication PDF (e.g., raw_docs/pub505.pdf)",
    )
    parser.add_argument(
        "--max-per-chapter",
        type=int,
        default=5,
        help="Maximum number of test cases to generate per chapter (default: 5)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Output directory for tests.json and answers.json (default: output/)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    pdf_path = args.pdf
    max_per_chapter = args.max_per_chapter
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not Path(pdf_path).exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        return

    # ── Initialize modules ──────────────────────────────────────────────────
    client = LLMClient()
    indexer = ChapterIndexer(client)
    builder = ScenarioBuilder(client)
    validator = Validator(client, builder)
    masker = Masker()

    # ── Step 1: Upload PDF & extract chapter index ───────────────────────────
    pdf_file = client.upload_pdf(pdf_path)
    chapters = indexer.extract_chapters(pdf_file)

    all_tests = []
    all_answers = []
    total_generated = 0
    total_skipped = 0

    # ── Steps 2-4: For each chapter, generate up to max_per_chapter cases ───
    for chapter in chapters:
        print(f"\n{'='*60}")
        print(f"Chapter: {chapter.get('title')} ({chapter.get('chapter_id')})")
        print(f"{'='*60}")

        chapter_count = 0
        while chapter_count < max_per_chapter:
            scenario = validator.validate_and_retry(chapter, pdf_file)

            if scenario is None:
                total_skipped += 1
                break  # All retries exhausted for this chapter slot; move on

            try:
                result = masker.apply(scenario)
            except ValueError as e:
                print(f"[Masker] Error: {e} — skipping this scenario.")
                total_skipped += 1
                continue

            all_tests.append(result["test_case"])
            all_answers.append(result["ground_truth"])
            chapter_count += 1
            total_generated += 1
            print(f"[Main] ✅ Generated test {total_generated}: {result['test_case']['id']}")

    # ── Step 5: Write output ─────────────────────────────────────────────────
    tests_path = output_dir / "tests.json"
    answers_path = output_dir / "answers.json"

    with open(tests_path, "w", encoding="utf-8") as f:
        json.dump(all_tests, f, ensure_ascii=False, indent=2)

    with open(answers_path, "w", encoding="utf-8") as f:
        json.dump(all_answers, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Done! Generated: {total_generated} | Skipped: {total_skipped}")
    print(f"📄 Tests  → {tests_path}")
    print(f"📄 Answers → {answers_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
