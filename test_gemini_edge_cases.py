"""
Test edge cases for Gemini markdown stripping logic.

This tests cases not covered in test_gemini_markdown_fix.py.
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


def test_edge_cases():
    """Test edge cases for markdown stripping."""

    # Edge case 1: Multiple backticks in a row
    test1 = "``````json\n{\"test\": \"value\"}\n```"
    print("Edge case 1: Extra backticks")
    result1 = strip_markdown_code_blocks(test1)
    print(f"Input: {test1[:50]}...")
    print(f"Result: {result1}")
    print(f"Starts with {{: {result1.startswith('{')}")

    # Edge case 2: Nested code blocks in JSON string
    test2 = "```json\n{\"code\": \"```python\\nprint()\\n```\"}\n```"
    print("\nEdge case 2: Nested code blocks in JSON string")
    result2 = strip_markdown_code_blocks(test2)
    print(f"Result: {result2}")
    try:
        parsed = json.loads(result2)
        print(f"[OK] JSON valid, has 'code': {'code' in parsed}")
    except Exception as e:
        print(f"[FAIL] JSON invalid: {e}")

    # Edge case 3: Whitespace before closing backticks
    test3 = "```json\n{\"test\": \"value\"}\n  ```  "
    print("\nEdge case 3: Whitespace around closing backticks")
    result3 = strip_markdown_code_blocks(test3)
    print(f"Result: [{result3}]")
    try:
        parsed = json.loads(result3)
        print("[OK] JSON valid")
    except Exception as e:
        print(f"[FAIL] JSON invalid: {e}")

    # Edge case 4: Only closing backticks (malformed)
    test4 = "{\"test\": \"value\"}\n```"
    print("\nEdge case 4: Only closing backticks (malformed)")
    result4 = strip_markdown_code_blocks(test4)
    print(f"Result: {result4}")
    print(f"Unchanged: {result4 == test4.strip()}")
    try:
        parsed = json.loads(result4)
        print("[OK] JSON still valid")
    except Exception as e:
        print(f"[FAIL] JSON invalid: {e}")

    # Edge case 5: Empty content between backticks
    test5 = "```json\n```"
    print("\nEdge case 5: Empty content between backticks")
    result5 = strip_markdown_code_blocks(test5)
    print(f"Result: [{result5}]")
    print(f"Empty: {result5 == ''}")

    # Edge case 6: Single line with backticks (no newlines)
    test6 = "```{\"test\": \"value\"}```"
    print("\nEdge case 6: Single line (no newlines)")
    result6 = strip_markdown_code_blocks(test6)
    print(f"Result: {result6}")
    print(f"[WARN] This is not properly handled - single line not split")

    # Edge case 7: Code block with language and extra text
    test7 = "```json\n{\"test\": \"value\"}\n```\nSome extra text after"
    print("\nEdge case 7: Extra text after closing backticks")
    result7 = strip_markdown_code_blocks(test7)
    print(f"Result: {result7}")
    try:
        parsed = json.loads(result7)
        print("[FAIL] Should not parse - has extra text")
    except Exception as e:
        print(f"[OK] Correctly fails to parse: {str(e)[:50]}")

    # Edge case 8: Indented code block
    test8 = "  ```json\n  {\"test\": \"value\"}\n  ```"
    print("\nEdge case 8: Indented code block")
    result8 = strip_markdown_code_blocks(test8)
    print(f"Result: {result8}")
    try:
        parsed = json.loads(result8)
        print("[OK] JSON valid despite indentation")
    except Exception as e:
        print(f"[FAIL] JSON invalid: {e}")

    # Edge case 9: Multiple JSON objects (invalid)
    test9 = "```json\n{\"test1\": 1}\n{\"test2\": 2}\n```"
    print("\nEdge case 9: Multiple JSON objects")
    result9 = strip_markdown_code_blocks(test9)
    print(f"Result: {result9}")
    try:
        parsed = json.loads(result9)
        print("[FAIL] Should not parse - multiple objects")
    except Exception as e:
        print(f"[OK] Correctly fails: {str(e)[:50]}")

    # Edge case 10: Closing backticks with spaces before newline
    test10 = "```json\n{\"test\": \"value\"}\n```   \n"
    print("\nEdge case 10: Closing backticks with trailing spaces")
    result10 = strip_markdown_code_blocks(test10)
    print(f"Result: [{result10}]")
    try:
        parsed = json.loads(result10)
        print("[OK] JSON valid")
    except Exception as e:
        print(f"[FAIL] JSON invalid: {e}")


if __name__ == "__main__":
    test_edge_cases()
