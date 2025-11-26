"""
Direct test of Gemini API to diagnose empty JSON responses.

This test bypasses all the layers (SEC processor, LLM service, etc.) to test
the Gemini API directly.
"""

import os
import asyncio


async def test_gemini_direct():
    """Test Gemini API directly with a simple prompt."""
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("[OK] Loaded .env file")
    except ImportError:
        print("[WARN] python-dotenv not installed, relying on system environment")

    api_key = os.getenv("GEMINI_API_KEY", "")

    print(f"GEMINI_API_KEY set: {bool(api_key)}")
    print(f"API key length: {len(api_key) if api_key else 0}")

    if not api_key:
        print("ERROR: GEMINI_API_KEY not set!")
        return

    try:
        import google.generativeai as genai
        print("[OK] google-generativeai library installed")
    except ImportError as e:
        print(f"[ERR] google-generativeai library NOT installed: {e}")
        print("\nInstall with: pip install google-generativeai")
        return

    try:
        # Configure API
        genai.configure(api_key=api_key)
        print("[OK] Gemini API configured")

        # List available models first
        print("\nAvailable Gemini models:")
        for model_info in genai.list_models():
            if "generateContent" in model_info.supported_generation_methods:
                print(f"  - {model_info.name}")

        # Create model - use gemini-2.0-flash-exp (latest stable)
        model_name = "gemini-2.0-flash-exp"
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 500,
            }
        )
        print(f"\n[OK] Model created: {model_name}")

        # Test prompt (simplified version of what SEC processor sends)
        prompt = """Analyze this SEC 8-K filing and extract key information.

Filing Type: 8-K
Item: 1.01
Title: Test Filing

Extract the following information in JSON format:

{
  "material_events": [],
  "financial_metrics": [],
  "sentiment": {
    "overall": "neutral",
    "confidence": 0.5
  },
  "summary": {
    "brief_summary": "Test response"
  }
}

Respond ONLY with valid JSON."""

        print("\n" + "="*60)
        print("Sending test prompt to Gemini...")
        print("="*60)

        # Generate response
        response = model.generate_content(prompt)

        print(f"\nResponse received")
        print(f"Has text attribute: {hasattr(response, 'text')}")

        if hasattr(response, "text"):
            text = response.text
            print(f"Response text length: {len(text)}")
            print(f"\nResponse text:\n{text}")

            # Try to parse as JSON
            import json
            try:
                parsed = json.loads(text)
                print(f"\n[OK] Successfully parsed as JSON")
                print(f"Keys: {list(parsed.keys())}")
            except json.JSONDecodeError as e:
                print(f"\n[ERR] Failed to parse as JSON: {e}")
        else:
            print("[ERR] Response has no text attribute")
            print(f"Response object: {response}")

            # Check for errors
            if hasattr(response, "prompt_feedback"):
                print(f"Prompt feedback: {response.prompt_feedback}")

            if hasattr(response, "candidates"):
                print(f"Candidates: {response.candidates}")
                for i, candidate in enumerate(response.candidates):
                    print(f"\nCandidate {i}:")
                    print(f"  Finish reason: {candidate.finish_reason}")
                    print(f"  Safety ratings: {candidate.safety_ratings}")
                    if hasattr(candidate, "content"):
                        print(f"  Content: {candidate.content}")

        # Check usage metadata
        if hasattr(response, "usage_metadata"):
            print(f"\nUsage metadata:")
            print(f"  Prompt tokens: {response.usage_metadata.prompt_token_count}")
            print(f"  Candidates tokens: {response.usage_metadata.candidates_token_count}")
            print(f"  Total tokens: {response.usage_metadata.total_token_count}")

    except Exception as e:
        print(f"\n[ERR] Error during Gemini API call: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_gemini_direct())
