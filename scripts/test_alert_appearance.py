#!/usr/bin/env python3
"""
Test Alert Appearance Tool
===========================

Sends dummy alerts to Discord with customizable parameters for testing and
fine-tuning alert appearance without waiting for real catalysts.

Usage:
    # Quick test with defaults
    python scripts/test_alert_appearance.py

    # Test specific ticker with custom parameters
    python scripts/test_alert_appearance.py --ticker ABCD --price 3.45 --volume 1500000 --catalyst fda

    # Use a preset scenario
    python scripts/test_alert_appearance.py --preset bullish_fda

    # Disable charts for faster iteration
    python scripts/test_alert_appearance.py --no-charts

    # Test negative alert
    python scripts/test_alert_appearance.py --preset bearish_offering

Available presets:
    - bullish_fda: FDA approval with strong metrics
    - bullish_partnership: Strategic partnership announcement
    - bullish_clinical: Phase 3 trial success
    - neutral_data: Neutral data presentation
    - bearish_offering: Dilutive offering warning
    - bearish_warrant: Warrant exercise alert
    - energy_discovery: Oil/gas discovery catalyst
    - tech_contract: Government contract win
    - compliance_regained: Nasdaq compliance regained
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from src.catalyst_bot.alerts import send_alert_safe
from src.catalyst_bot.config import get_settings


# Preset scenarios for quick testing
PRESETS = {
    "bullish_fda": {
        "ticker": "ABCD",
        "title": "ABCD Receives FDA Breakthrough Therapy Designation for Lead Drug Candidate",
        "price": 2.45,
        "prev_close": 1.85,
        "volume": 5000000,
        "avg_volume": 800000,
        "catalyst_type": "FDA approval",
        "sentiment": 0.85,
        "score": 8.5,
        "reason": "FDA breakthrough designation significantly accelerates development timeline. "
                  "Strong clinical efficacy data supports rapid approval pathway.",
        "is_negative": False,
        "rvol": 6.25,
        "llm_analysis": "This is a highly bullish catalyst. Breakthrough therapy designation is "
                       "granted by FDA when preliminary clinical evidence demonstrates substantial "
                       "improvement over existing therapies. This designation provides: 1) More frequent "
                       "FDA interaction, 2) Rolling review of NDA submission, 3) Priority review status. "
                       "Historical analysis shows stocks receiving BTD average 40-60% gains within 30 days.",
    },
    "bullish_partnership": {
        "ticker": "WXYZ",
        "title": "WXYZ Announces Strategic Partnership with Major Pharmaceutical Company",
        "price": 1.75,
        "prev_close": 1.50,
        "volume": 3200000,
        "avg_volume": 450000,
        "catalyst_type": "partnership",
        "sentiment": 0.72,
        "score": 7.8,
        "reason": "Major pharma partnership validates technology platform and provides significant "
                  "capital for development programs.",
        "is_negative": False,
        "rvol": 7.1,
        "llm_analysis": "Strategic partnerships with big pharma are strong validation events. "
                       "This partnership likely includes upfront payment, milestone payments, and "
                       "royalties. Reduces financial risk and provides expertise for regulatory process.",
    },
    "bullish_clinical": {
        "ticker": "EFGH",
        "title": "EFGH Reports Positive Phase 3 Results - Primary Endpoint Met with Statistical Significance",
        "price": 4.20,
        "prev_close": 3.10,
        "volume": 8500000,
        "avg_volume": 1200000,
        "catalyst_type": "clinical trial",
        "sentiment": 0.90,
        "score": 9.2,
        "reason": "Phase 3 success with strong statistical significance (p<0.001). Primary and "
                  "secondary endpoints both met. Safety profile favorable.",
        "is_negative": False,
        "rvol": 7.08,
        "llm_analysis": "Phase 3 trial success is the most important de-risking event for biotech stocks. "
                       "Meeting primary endpoint with high statistical significance dramatically increases "
                       "approval probability. Market typically assigns 60-80% probability of approval post "
                       "positive Phase 3. Expected value increase of 100-200% over 6-12 months.",
    },
    "neutral_data": {
        "ticker": "MNOP",
        "title": "MNOP Provides Q4 Business Update and 2024 Guidance",
        "price": 5.60,
        "prev_close": 5.55,
        "volume": 950000,
        "avg_volume": 750000,
        "catalyst_type": "earnings",
        "sentiment": 0.15,
        "score": 4.2,
        "reason": "Routine business update with mixed metrics. Some positive developments offset by "
                  "delayed timelines on key programs.",
        "is_negative": False,
        "rvol": 1.27,
        "llm_analysis": "Mixed catalyst with balanced positive and negative elements. Volume spike "
                       "suggests some investor interest but sentiment is neutral. May set up for "
                       "future moves if upcoming catalysts are positive.",
    },
    "bearish_offering": {
        "ticker": "DILU",
        "title": "DILU Announces $15M Registered Direct Offering Priced At-The-Market",
        "price": 1.20,
        "prev_close": 1.85,
        "volume": 12000000,
        "avg_volume": 2000000,
        "catalyst_type": "offering",
        "sentiment": -0.75,
        "score": -6.5,
        "reason": "Dilutive at-the-market offering with poor pricing. Indicates financial distress "
                  "and significant shareholder dilution imminent.",
        "is_negative": True,
        "rvol": 6.0,
        "llm_analysis": "NEGATIVE CATALYST - EXIT SIGNAL. At-the-market offerings priced below market "
                       "are highly dilutive. Share count will increase significantly, reducing existing "
                       "shareholder value. This pricing suggests company had limited negotiating power "
                       "and may indicate cash flow problems. Historical data shows 60-80% of stocks "
                       "continue declining 30 days post-offering.",
        "negative_keywords": ["offering_negative", "dilution_negative"],
    },
    "bearish_warrant": {
        "ticker": "WRNT",
        "title": "WRNT Announces Warrant Exercise Agreement with Pre-Funded Warrants",
        "price": 0.85,
        "prev_close": 1.05,
        "volume": 8000000,
        "avg_volume": 1500000,
        "catalyst_type": "warrant",
        "sentiment": -0.60,
        "score": -5.8,
        "reason": "Pre-funded warrant exercise indicates dilution. Existing shareholders will see "
                  "ownership percentage decrease.",
        "is_negative": True,
        "rvol": 5.33,
        "llm_analysis": "NEGATIVE CATALYST - DILUTION ALERT. Warrant exercises increase outstanding share "
                       "count without providing significant new capital to the company (pre-funded warrants "
                       "were already paid). This is pure dilution for existing holders. Expect continued "
                       "selling pressure as new shares hit the market.",
        "negative_keywords": ["warrant_negative", "dilution_negative"],
    },
    "energy_discovery": {
        "ticker": "OILX",
        "title": "OILX Reports Major Oil Discovery at Exploration Well - Initial Flow Tests Exceed Expectations",
        "price": 3.80,
        "prev_close": 2.20,
        "volume": 15000000,
        "avg_volume": 2500000,
        "catalyst_type": "oil discovery",
        "sentiment": 0.88,
        "score": 9.0,
        "reason": "Major oil discovery with exceptional flow test results. Reserves estimate suggests "
                  "multi-year production potential. Transforms company valuation.",
        "is_negative": False,
        "rvol": 6.0,
        "llm_analysis": "High-impact energy discovery catalyst. Flow test results exceeding expectations "
                       "suggests significant reserves. Energy discoveries have historically strong returns "
                       "(274.6% average from MOA analysis). This type of catalyst often triggers sustained "
                       "multi-month rallies as market reprices asset value.",
    },
    "tech_contract": {
        "ticker": "GOVX",
        "title": "GOVX Wins $25M Federal Government Cloud Infrastructure Contract",
        "price": 4.50,
        "prev_close": 3.40,
        "volume": 4500000,
        "avg_volume": 800000,
        "catalyst_type": "government contract",
        "sentiment": 0.78,
        "score": 8.3,
        "reason": "Multi-year government contract provides recurring revenue stream and validates "
                  "technology platform. Opens door for additional federal contracts.",
        "is_negative": False,
        "rvol": 5.63,
        "llm_analysis": "Government contracts are high-value catalysts (54.9% average returns). Multi-year "
                       "contract provides revenue visibility and reduces execution risk. Government business "
                       "often leads to additional awards through existing vendor relationships. Strong "
                       "validation of technology capabilities.",
    },
    "compliance_regained": {
        "ticker": "CMPL",
        "title": "CMPL Regains Nasdaq Compliance - Minimum Bid Price Requirement Met",
        "price": 1.15,
        "prev_close": 0.95,
        "volume": 2800000,
        "avg_volume": 650000,
        "catalyst_type": "compliance",
        "sentiment": 0.55,
        "score": 6.2,
        "reason": "Successfully regained Nasdaq listing compliance by meeting minimum bid price "
                  "requirement. Removes delisting risk and restores institutional investor eligibility.",
        "is_negative": False,
        "rvol": 4.31,
        "llm_analysis": "Compliance restoration removes significant overhang. Delisting risk was pressuring "
                       "stock as institutions must sell upon delisting. Regaining compliance restores access "
                       "to institutional capital and removes forced selling pressure. Often marks bottom "
                       "for distressed names.",
    },
}


def create_dummy_item(
    ticker: str = "TEST",
    title: str = "Test Alert - Catalyst Event Detected",
    price: float = 2.50,
    prev_close: float = 2.00,
    volume: int = 1000000,
    avg_volume: int = 500000,
    catalyst_type: str = "general",
    sentiment: float = 0.5,
    score: float = 6.0,
    reason: Optional[str] = None,
    is_negative: bool = False,
    rvol: Optional[float] = None,
    llm_analysis: Optional[str] = None,
    negative_keywords: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Create a dummy item dictionary matching the structure expected by send_alert_safe.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol
    title : str
        Alert headline/title
    price : float
        Current price
    prev_close : float
        Previous close price
    volume : int
        Current volume
    avg_volume : int
        Average volume
    catalyst_type : str
        Type of catalyst (fda, partnership, clinical, etc.)
    sentiment : float
        Sentiment score (-1.0 to 1.0)
    score : float
        Catalyst score
    reason : str, optional
        Analysis reason text
    is_negative : bool
        Whether this is a negative catalyst (offering, dilution, etc.)
    rvol : float, optional
        Relative volume multiplier
    llm_analysis : str, optional
        LLM analysis text
    negative_keywords : list, optional
        List of negative keyword categories that triggered alert

    Returns
    -------
    dict
        Item dictionary ready for send_alert_safe
    """
    # Calculate price change
    change_pct = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

    # Calculate RVol if not provided
    if rvol is None:
        rvol = volume / avg_volume if avg_volume > 0 else 1.0

    # Build item dictionary
    item = {
        "ticker": ticker,
        "title": title,
        "link": f"https://example.com/news/{ticker.lower()}-test-alert",
        "pubDate": datetime.now(timezone.utc).isoformat(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "Test Generator",
        "price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "volume": volume,
        "avg_volume": avg_volume,
        "rvol": rvol,
        "sentiment": sentiment,
        "catalyst_type": catalyst_type,
        "reason": reason,  # Add reason to item dict for embed display
        "summary": llm_analysis or f"This is a test alert for {ticker} demonstrating {catalyst_type} catalyst. "
                   f"The stock is trading at ${price:.2f}, up {change_pct:.1f}% with {rvol:.1f}x normal volume.",
    }

    # Create scored object with score and reason
    scored_obj = {
        "score": score,
        "reason": reason or f"Test catalyst of type '{catalyst_type}'",
        "sentiment": sentiment,
        # Add RVol data for rich alerts
        "rvol": rvol,
        "current_volume": volume,
        "avg_volume_20d": avg_volume,
        # Add float data (demonstrates squeeze potential)
        "float_shares": 4.8e6 if price < 3.0 else 15.2e6,  # Low float for penny stocks
        "float_class": "LOW_FLOAT" if price < 3.0 else "MEDIUM_FLOAT",
        "short_interest_pct": 18.5 if sentiment > 0.5 else 8.2,  # High SI for bullish catalysts
        "shares_outstanding": 8.5e6 if price < 3.0 else 25.0e6,
        "institutional_ownership_pct": 12.3,
    }

    # Classify RVol for display
    if rvol >= 5.0:
        scored_obj["rvol_class"] = "EXTREME_RVOL"
    elif rvol >= 3.0:
        scored_obj["rvol_class"] = "HIGH_RVOL"
    elif rvol >= 1.5:
        scored_obj["rvol_class"] = "ELEVATED_RVOL"
    elif rvol >= 0.5:
        scored_obj["rvol_class"] = "NORMAL_RVOL"
    else:
        scored_obj["rvol_class"] = "LOW_RVOL"

    # Add negative alert fields if applicable
    if is_negative:
        scored_obj["is_negative_alert"] = True
        scored_obj["alert_type"] = "NEGATIVE"
        scored_obj["negative_keywords"] = negative_keywords or []

    # Add LLM analysis if provided
    if llm_analysis:
        item["llm_sentiment"] = sentiment
        item["llm_explanation"] = llm_analysis
        scored_obj["llm_analysis"] = llm_analysis

    # Add some realistic indicator values
    item["vwap"] = price * 0.98  # VWAP slightly below current price
    item["rsi"] = 55.0 + (sentiment * 20.0)  # RSI correlates with sentiment

    return {"item": item, "scored": scored_obj}


def main():
    """Main entry point for test alert appearance tool."""
    parser = argparse.ArgumentParser(
        description="Send dummy alerts to Discord for appearance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Preset or custom mode
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        help="Use a preset scenario",
    )

    # Custom parameters
    parser.add_argument("--ticker", help="Stock ticker symbol")
    parser.add_argument("--title", help="Alert title/headline")
    parser.add_argument("--price", type=float, help="Current price")
    parser.add_argument("--prev-close", type=float, help="Previous close price")
    parser.add_argument("--volume", type=int, help="Current volume")
    parser.add_argument("--avg-volume", type=int, help="Average volume")
    parser.add_argument("--catalyst", help="Catalyst type (fda, partnership, etc.)")
    parser.add_argument(
        "--sentiment",
        type=float,
        help="Sentiment score (-1.0 to 1.0)",
    )
    parser.add_argument("--score", type=float, help="Catalyst score (0-10)")
    parser.add_argument("--reason", help="Analysis reason text")
    parser.add_argument(
        "--negative",
        action="store_true",
        help="Make this a negative alert (offering, dilution, etc.)",
    )
    parser.add_argument(
        "--llm-analysis",
        help="Custom LLM analysis text",
    )

    # Feature toggles
    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="Disable chart generation for faster iteration",
    )
    parser.add_argument(
        "--webhook",
        help="Override Discord webhook URL (defaults to DISCORD_WEBHOOK_URL from .env)",
    )

    # List presets
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List all available preset scenarios and exit",
    )

    args = parser.parse_args()

    # List presets and exit
    if args.list_presets:
        print("\nAvailable Preset Scenarios:")
        print("=" * 60)
        for name, preset in PRESETS.items():
            print(f"\n{name}:")
            print(f"  Ticker: {preset['ticker']}")
            print(f"  Title: {preset['title'][:70]}...")
            print(f"  Type: {preset['catalyst_type']}")
            print(f"  Sentiment: {preset['sentiment']:.2f}")
            print(f"  Score: {preset['score']:.1f}")
            print(f"  Negative: {preset['is_negative']}")
        print("\n" + "=" * 60)
        return

    # Load settings
    settings = get_settings()

    # Temporarily disable charts if requested
    original_charts = settings.feature_rich_alerts
    original_quickchart = settings.feature_quickchart
    original_finviz = settings.feature_finviz_chart

    if args.no_charts:
        print("Charts disabled for faster iteration")
        settings.feature_rich_alerts = False
        settings.feature_quickchart = False
        settings.feature_finviz_chart = False

    # Use preset or custom parameters
    if args.preset:
        print(f"Using preset: {args.preset}")
        params = PRESETS[args.preset].copy()
    else:
        # Build custom params from arguments
        params = {
            "ticker": args.ticker or "TEST",
            "title": args.title or "Test Alert - Catalyst Event Detected",
            "price": args.price or 2.50,
            "prev_close": args.prev_close or 2.00,
            "volume": args.volume or 1000000,
            "avg_volume": args.avg_volume or 500000,
            "catalyst_type": args.catalyst or "general",
            "sentiment": args.sentiment if args.sentiment is not None else 0.5,
            "score": args.score or 6.0,
            "reason": args.reason,
            "is_negative": args.negative,
            "llm_analysis": args.llm_analysis,
        }

    # Create dummy item
    dummy_data = create_dummy_item(**params)

    # Override webhook if specified
    original_webhook = settings.discord_webhook_url
    if args.webhook:
        settings.discord_webhook_url = args.webhook
        print(f"Using custom webhook: {args.webhook[:50]}...")

    # Verify webhook is configured
    if not settings.discord_webhook_url:
        print("ERROR: No Discord webhook configured!")
        print("   Set DISCORD_WEBHOOK_URL in your .env file or use --webhook")
        return

    # Send the alert
    print(f"\nSending test alert for {params['ticker']}...")
    print(f"   Title: {params['title'][:60]}...")
    print(f"   Price: ${params['price']:.2f} (change: {dummy_data['item']['change_pct']:+.2f}%)")
    print(f"   Volume: {params['volume']:,} (RVol: {dummy_data['item']['rvol']:.2f}x)")
    print(f"   Sentiment: {params['sentiment']:.2f}")
    print(f"   Score: {params['score']:.1f}")
    print(f"   Negative Alert: {params['is_negative']}")

    try:
        # Extract price and change_pct from item for send_alert_safe
        item = dummy_data["item"]
        last_price = item.get("price")
        last_change_pct = item.get("change_pct")

        success = send_alert_safe(
            item,
            dummy_data["scored"],
            last_price,
            last_change_pct
        )
        if success:
            print("\nAlert sent successfully!")
            print("   Check your Discord channel to verify appearance.")
        else:
            print("\nWarning: Alert may not have been sent (check logs)")
            print("   Verify webhook URL and Discord channel permissions.")
    except Exception as e:
        print(f"\nError sending alert: {e}")
        import traceback
        traceback.print_exc()

    # Restore original settings
    if args.no_charts:
        settings.feature_rich_alerts = original_charts
        settings.feature_quickchart = original_quickchart
        settings.feature_finviz_chart = original_finviz

    if args.webhook:
        settings.discord_webhook_url = original_webhook


if __name__ == "__main__":
    main()
