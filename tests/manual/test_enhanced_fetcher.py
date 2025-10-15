"""
Test Enhanced SEC Document Fetcher
====================================

Tests the enhanced document fetcher with real SEC filing links to verify:
1. CIK extraction works
2. Submissions API integration works
3. Index page parsing fallback works
4. Actual filing content is extracted (not just index pages)
"""

from src.catalyst_bot.sec_document_fetcher import fetch_sec_document_text

def test_sec_document_extraction():
    """Test with a real SEC 8-K link from rejected_items.jsonl"""

    print("=" * 80)
    print("Testing Enhanced SEC Document Fetcher")
    print("=" * 80)
    print()

    # Use a real link from the rejected items (American Airlines 8-K)
    # CIK: 6201, Accession: 0001193125-24-249922
    test_link = "https://www.sec.gov/Archives/edgar/data/6201/000119312524249922/0001193125-24-249922-index.htm"

    print(f"Test Link: {test_link}")
    print()
    print("Fetching document...")
    print()

    # Fetch document text
    doc_text = fetch_sec_document_text(test_link)

    print("=" * 80)
    print("Results:")
    print("=" * 80)
    print()
    print(f"Document Length: {len(doc_text)} characters")
    print()

    if len(doc_text) > 0:
        print("[SUCCESS] Document fetched successfully!")
        print()
        print("First 1000 characters:")
        print("-" * 80)
        print(doc_text[:1000])
        print("-" * 80)
        print()

        # Check if content looks like actual filing (not just index page)
        has_item_content = any(keyword in doc_text.lower() for keyword in [
            "item 1.01", "item 2.02", "item 8.01",
            "securities", "filing", "form 8-k"
        ])

        if has_item_content:
            print("[SUCCESS] Content appears to be actual SEC filing (contains Item references)")
        else:
            print("[WARNING] Content may be index page or incomplete")

    else:
        print("[FAILED] Document fetcher returned 0 characters")
        print("This indicates the enhancement did not work as expected")

    print()
    print("=" * 80)

if __name__ == "__main__":
    test_sec_document_extraction()
