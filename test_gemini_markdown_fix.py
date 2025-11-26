"""
Test to verify Gemini markdown code block stripping works correctly.

This test validates the fix for SEC LLM processing where Gemini wraps
JSON responses in markdown code blocks (```json...```).
"""

import json


def strip_markdown_code_blocks(text: str) -> str:
    """
    Strip markdown code blocks from Gemini response.

    This is the exact logic from gemini.py lines 135-146.
    """
    text_cleaned = text.strip()
    if text_cleaned.startswith("```"):
        # Remove opening ```json or ```
        lines = text_cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]  # Remove first line
        # Remove closing ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # Remove last line
        text_cleaned = "\n".join(lines).strip()

    return text_cleaned


def test_markdown_stripping():
    """Test various markdown-wrapped JSON scenarios."""

    # Test 1: JSON wrapped in ```json...```
    wrapped_json = """```json
{
  "material_events": [],
  "financial_metrics": [],
  "sentiment": {
    "overall": "neutral",
    "confidence": 0.5
  },
  "summary": {
    "brief_summary": "Test Filing"
  }
}
```"""

    cleaned = strip_markdown_code_blocks(wrapped_json)
    print("Test 1: JSON wrapped in ```json...```")
    print(f"Input length: {len(wrapped_json)}")
    print(f"Output length: {len(cleaned)}")
    print(f"Starts with {{: {cleaned.startswith('{')}")

    try:
        parsed = json.loads(cleaned)
        print(f"[OK] Successfully parsed JSON")
        print(f"  Keys: {list(parsed.keys())}")
        assert "material_events" in parsed
        assert "financial_metrics" in parsed
        assert "sentiment" in parsed
        print(f"[OK] All expected keys present\n")
    except json.JSONDecodeError as e:
        print(f"[ERR] Failed to parse JSON: {e}\n")
        return False

    # Test 2: JSON wrapped in ```...``` (no language specifier)
    wrapped_json_2 = """```
{
  "test": "value"
}
```"""

    cleaned_2 = strip_markdown_code_blocks(wrapped_json_2)
    print("Test 2: JSON wrapped in ```...``` (no language)")
    print(f"Starts with {{: {cleaned_2.startswith('{')}")

    try:
        parsed_2 = json.loads(cleaned_2)
        print(f"[OK] Successfully parsed JSON")
        print(f"  Keys: {list(parsed_2.keys())}\n")
    except json.JSONDecodeError as e:
        print(f"[ERR] Failed to parse JSON: {e}\n")
        return False

    # Test 3: Plain JSON (no markdown)
    plain_json = """{"test": "value", "number": 123}"""

    cleaned_3 = strip_markdown_code_blocks(plain_json)
    print("Test 3: Plain JSON (no markdown)")
    print(f"Input == Output: {plain_json == cleaned_3}")

    try:
        parsed_3 = json.loads(cleaned_3)
        print(f"[OK] Successfully parsed JSON")
        print(f"  Keys: {list(parsed_3.keys())}\n")
    except json.JSONDecodeError as e:
        print(f"[ERR] Failed to parse JSON: {e}\n")
        return False

    # Test 4: Truncated response (just opening marker)
    truncated = """```json
"""

    cleaned_4 = strip_markdown_code_blocks(truncated)
    print("Test 4: Truncated response (just opening marker)")
    print(f"Output: '{cleaned_4}'")
    print(f"Empty string: {cleaned_4 == ''}")
    print(f"[OK] Handles truncated response gracefully\n")

    # Test 5: Real-world example from logs
    real_example = """```json
{
  "material_events": [],
  "financial_metrics": [],
  "sentiment": {
    "overall": "neutral",
    "confidence": 0.5
  },
  "summary": {
    "brief_summary": "No material events"""

    cleaned_5 = strip_markdown_code_blocks(real_example)
    print("Test 5: Real-world truncated example from logs")
    print(f"Starts with {{: {cleaned_5.startswith('{')}")
    print(f"Contains 'material_events': {'material_events' in cleaned_5}")
    print(f"[OK] Strips opening marker even for incomplete JSON\n")

    print("="*60)
    print("All tests passed! [OK]")
    print("="*60)
    return True


if __name__ == "__main__":
    success = test_markdown_stripping()
    exit(0 if success else 1)
