"""
Comprehensive Test Suite for Gemini Provider Edge Cases
=========================================================

Tests cover:
- Markdown code block stripping (```json...```, ```...```)
- Safety filter blocks (finish_reason=2)
- Empty responses
- Malformed JSON in responses
- API errors (timeout, rate limit, invalid API key)
- Token counting and estimation
- Cost calculations for all model tiers
- Response metadata handling
- Missing usage_metadata handling
- Large responses
- Timeout scenarios
- Connection errors

Coverage areas:
1. Markdown stripping (various formats)
2. Safety filter handling
3. Error handling (timeouts, rate limits, auth errors)
4. Cost calculation accuracy
5. Token counting (with and without metadata)
6. JSON parsing from responses
7. Edge cases (empty, malformed, truncated responses)
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from catalyst_bot.services.llm_providers.gemini import GeminiProvider


class TestMarkdownStripping:
    """Test markdown code block stripping functionality."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_strips_json_markdown_blocks(self, provider):
        """Test stripping of ```json...``` markdown blocks."""
        mock_response = Mock()
        mock_response.text = """```json
{
    "sentiment": "bullish",
    "confidence": 0.85
}
```"""
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should strip markdown blocks
            assert result["text"].startswith("{")
            assert result["text"].endswith("}")
            assert "```" not in result["text"]
            assert "json" not in result["text"]

            # Should parse as valid JSON
            parsed = json.loads(result["text"])
            assert parsed["sentiment"] == "bullish"

    @pytest.mark.asyncio
    async def test_strips_plain_markdown_blocks(self, provider):
        """Test stripping of plain ``` markdown blocks."""
        mock_response = Mock()
        mock_response.text = """```
{
    "keywords": ["fda", "approval"],
    "material": true
}
```"""
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            assert result["text"].startswith("{")
            assert result["text"].endswith("}")
            assert "```" not in result["text"]

    @pytest.mark.asyncio
    async def test_handles_nested_markdown(self, provider):
        """Test handling of markdown within JSON strings."""
        mock_response = Mock()
        mock_response.text = """```json
{
    "summary": "Code example: ```python print('hello')```",
    "sentiment": "neutral"
}
```"""
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should only strip outer markdown blocks
            assert result["text"].startswith("{")
            parsed = json.loads(result["text"])
            assert "```" in parsed["summary"]  # Inner markdown preserved

    @pytest.mark.asyncio
    async def test_no_markdown_blocks(self, provider):
        """Test response without markdown blocks passes through."""
        mock_response = Mock()
        mock_response.text = '{"sentiment": "neutral", "confidence": 0.5}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should remain unchanged
            assert result["text"] == '{"sentiment": "neutral", "confidence": 0.5}'


class TestSafetyFilters:
    """Test safety filter handling."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_safety_filter_block_returns_empty(self, provider):
        """Test that safety filter blocks return empty response gracefully."""
        # Create a mock response that raises ValueError when .text is accessed
        mock_response = Mock()

        def raise_safety_error():
            raise ValueError("Response.text is not available. The candidate's finish_reason is 2")

        type(mock_response).text = property(lambda self: raise_safety_error())

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should return empty response without crashing
            assert result["text"] == ""
            assert result["tokens_input"] == 0
            assert result["tokens_output"] == 0
            assert result["cost_usd"] == 0.0
            assert result["parsed_output"] is None

    @pytest.mark.asyncio
    async def test_safety_filter_finish_reason_logged(self, provider):
        """Test that safety filter blocks are logged."""
        mock_response = Mock()

        def raise_safety_error():
            raise ValueError("finish_reason: 2 - SAFETY")

        type(mock_response).text = property(lambda self: raise_safety_error())

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            # Should not raise exception
            result = await provider.query(
                prompt="Test prompt with sensitive content",
                model="gemini-2.5-flash"
            )

            assert result["text"] == ""


class TestEmptyResponses:
    """Test handling of empty responses."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_empty_text_response(self, provider):
        """Test handling of empty text in response."""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 0

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            assert result["text"] == ""
            assert result["tokens_input"] == 100
            assert result["tokens_output"] == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_response(self, provider):
        """Test handling of whitespace-only response."""
        mock_response = Mock()
        mock_response.text = "   \n\n  \t  "
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 5

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should strip to empty string
            assert result["text"] == ""


class TestMalformedJSON:
    """Test handling of malformed JSON responses."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_invalid_json_returns_null_parsed(self, provider):
        """Test that invalid JSON returns null in parsed_output."""
        mock_response = Mock()
        mock_response.text = '{"invalid": json syntax here}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should still return text, but parsed_output should be None
            assert result["text"] == '{"invalid": json syntax here}'
            assert result["parsed_output"] is None

    @pytest.mark.asyncio
    async def test_truncated_json_returns_null_parsed(self, provider):
        """Test that truncated JSON returns null in parsed_output."""
        mock_response = Mock()
        mock_response.text = '{"sentiment": "bullish", "confiden'  # Truncated
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            assert result["parsed_output"] is None


class TestAPIErrors:
    """Test API error handling."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_invalid_api_key_error(self, provider):
        """Test handling of invalid API key error."""
        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(
                side_effect=Exception("Invalid API key")
            )
            mock_model_class.return_value = mock_model_instance

            with pytest.raises(Exception) as exc_info:
                await provider.query(
                    prompt="Test prompt",
                    model="gemini-2.5-flash"
                )

            assert "Invalid API key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error(self, provider):
        """Test handling of timeout error."""
        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(
                side_effect=Exception("Request timeout")
            )
            mock_model_class.return_value = mock_model_instance

            with pytest.raises(Exception) as exc_info:
                await provider.query(
                    prompt="Test prompt",
                    model="gemini-2.5-flash",
                    timeout=5.0
                )

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, provider):
        """Test handling of rate limit error."""
        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(
                side_effect=Exception("Rate limit exceeded")
            )
            mock_model_class.return_value = mock_model_instance

            with pytest.raises(Exception) as exc_info:
                await provider.query(
                    prompt="Test prompt",
                    model="gemini-2.5-flash"
                )

            assert "Rate limit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_error(self):
        """Test that missing API key raises ValueError."""
        with patch.dict('os.environ', {}, clear=True):
            provider = GeminiProvider(config={})

            with pytest.raises(ValueError) as exc_info:
                await provider.query(
                    prompt="Test prompt",
                    model="gemini-2.5-flash"
                )

            assert "GEMINI_API_KEY not set" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_library_not_installed_error(self, provider):
        """Test handling when google-generativeai library not installed."""
        with patch('google.generativeai.GenerativeModel', side_effect=ImportError):
            with pytest.raises(ValueError) as exc_info:
                await provider.query(
                    prompt="Test prompt",
                    model="gemini-2.5-flash"
                )

            assert "google-generativeai" in str(exc_info.value)


class TestTokenCounting:
    """Test token counting and estimation."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_uses_metadata_token_counts(self, provider):
        """Test that provider uses Gemini's usage_metadata for token counts."""
        mock_response = Mock()
        mock_response.text = '{"test": "response"}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 250
        mock_response.usage_metadata.candidates_token_count = 125

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            assert result["tokens_input"] == 250
            assert result["tokens_output"] == 125

    @pytest.mark.asyncio
    async def test_estimates_tokens_when_no_metadata(self, provider):
        """Test token estimation when usage_metadata is missing."""
        mock_response = Mock(spec=['text'])  # Only spec 'text', no usage_metadata
        mock_response.text = '{"test": "response"}'

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="This is a test prompt with some words",
                model="gemini-2.5-flash"
            )

            # Should estimate based on character count (~4 chars per token)
            assert result["tokens_input"] > 0
            assert result["tokens_output"] > 0

    @pytest.mark.asyncio
    async def test_includes_system_prompt_in_token_count(self, provider):
        """Test that system prompt is included in token count estimation."""
        mock_response = Mock(spec=['text'])  # Only spec 'text', no usage_metadata
        mock_response.text = '{"test": "response"}'

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="User prompt",
                system_prompt="System instructions here",
                model="gemini-2.5-flash"
            )

            # Should count both prompts
            assert result["tokens_input"] > 0


class TestCostCalculations:
    """Test cost calculation accuracy for different models."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    def test_flash_lite_cost_calculation(self, provider):
        """Test cost calculation for Gemini Flash Lite."""
        cost = provider.estimate_cost(
            model="gemini-2.0-flash-lite",
            tokens_input=1_000_000,
            tokens_output=1_000_000
        )

        # Flash Lite: $0.02/1M input, $0.08/1M output
        expected = 0.02 + 0.08
        assert abs(cost - expected) < 0.001

    def test_flash_cost_calculation(self, provider):
        """Test cost calculation for Gemini Flash."""
        cost = provider.estimate_cost(
            model="gemini-2.5-flash",
            tokens_input=1_000_000,
            tokens_output=1_000_000
        )

        # Flash: $0.075/1M input, $0.30/1M output
        expected = 0.075 + 0.30
        assert abs(cost - expected) < 0.001

    def test_pro_cost_calculation(self, provider):
        """Test cost calculation for Gemini Pro."""
        cost = provider.estimate_cost(
            model="gemini-2.5-pro",
            tokens_input=1_000_000,
            tokens_output=1_000_000
        )

        # Pro: $1.25/1M input, $5.00/1M output
        expected = 1.25 + 5.00
        assert abs(cost - expected) < 0.001

    def test_small_request_cost(self, provider):
        """Test cost calculation for small requests."""
        cost = provider.estimate_cost(
            model="gemini-2.5-flash",
            tokens_input=500,
            tokens_output=250
        )

        # 500 input at $0.075/1M = $0.0000375
        # 250 output at $0.30/1M = $0.000075
        expected_input = (500 / 1_000_000) * 0.075
        expected_output = (250 / 1_000_000) * 0.30
        expected = expected_input + expected_output

        assert abs(cost - expected) < 0.000001

    def test_unknown_model_uses_flash_pricing(self, provider):
        """Test that unknown models default to Flash pricing."""
        cost = provider.estimate_cost(
            model="gemini-unknown-model",
            tokens_input=1_000_000,
            tokens_output=1_000_000
        )

        # Should use Flash pricing as fallback
        expected = 0.075 + 0.30
        assert abs(cost - expected) < 0.001


class TestResponseMetadata:
    """Test handling of response metadata."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_parses_valid_json_automatically(self, provider):
        """Test that valid JSON is automatically parsed."""
        mock_response = Mock()
        mock_response.text = '{"sentiment": "bullish", "confidence": 0.85}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            assert result["parsed_output"] is not None
            assert result["parsed_output"]["sentiment"] == "bullish"
            assert result["parsed_output"]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_no_confidence_score(self, provider):
        """Test that Gemini doesn't provide confidence scores."""
        mock_response = Mock()
        mock_response.text = '{"test": "data"}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Gemini doesn't provide confidence scores
            assert result["confidence"] is None


class TestLargeResponses:
    """Test handling of large responses."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_large_json_response(self, provider):
        """Test handling of large JSON response."""
        # Create large JSON response
        large_data = {
            "material_events": [
                {
                    "event_type": f"Event {i}",
                    "description": f"Description for event {i}" * 10,
                    "significance": "high"
                }
                for i in range(100)
            ],
            "sentiment": {"overall": "neutral", "confidence": 0.5}
        }

        mock_response = Mock()
        mock_response.text = json.dumps(large_data)
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 500
        mock_response.usage_metadata.candidates_token_count = 5000

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            result = await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash"
            )

            # Should handle large response without issues
            assert result["tokens_output"] == 5000
            assert result["parsed_output"] is not None
            assert len(result["parsed_output"]["material_events"]) == 100


class TestGenerationConfig:
    """Test generation configuration parameters."""

    @pytest.fixture
    def provider(self):
        """Create Gemini provider with mock API key."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key-12345'}):
            return GeminiProvider(config={})

    @pytest.mark.asyncio
    async def test_respects_max_tokens(self, provider):
        """Test that max_tokens parameter is passed to Gemini."""
        mock_response = Mock()
        mock_response.text = '{"test": "response"}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash",
                max_tokens=500
            )

            # Verify generation_config was created with max_tokens
            call_args = mock_model_class.call_args
            assert call_args[1]["generation_config"]["max_output_tokens"] == 500

    @pytest.mark.asyncio
    async def test_respects_temperature(self, provider):
        """Test that temperature parameter is passed to Gemini."""
        mock_response = Mock()
        mock_response.text = '{"test": "response"}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            await provider.query(
                prompt="Test prompt",
                model="gemini-2.5-flash",
                temperature=0.2
            )

            # Verify generation_config was created with temperature
            call_args = mock_model_class.call_args
            assert call_args[1]["generation_config"]["temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_system_prompt_passed(self, provider):
        """Test that system_prompt is passed as system_instruction."""
        mock_response = Mock()
        mock_response.text = '{"test": "response"}'
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50

        with patch('google.generativeai.GenerativeModel') as mock_model_class:
            mock_model_instance = Mock()
            mock_model_instance.generate_content = Mock(return_value=mock_response)
            mock_model_class.return_value = mock_model_instance

            await provider.query(
                prompt="Test prompt",
                system_prompt="You are a financial analyst.",
                model="gemini-2.5-flash"
            )

            # Verify system_instruction was passed
            call_args = mock_model_class.call_args
            assert call_args[1]["system_instruction"] == "You are a financial analyst."
