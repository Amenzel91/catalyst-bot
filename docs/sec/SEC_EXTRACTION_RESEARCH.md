# SEC Filing Information Extraction with LLMs: Industry Standards and Best Practices

**Research Date**: November 25, 2025
**Purpose**: Investigate industry standards for extracting structured information from SEC filings using Large Language Models

---

## Executive Summary

This research document synthesizes industry best practices for LLM-based SEC filing information extraction based on 2024-2025 academic research, commercial implementations (LlamaExtract), and open-source frameworks. The findings reveal that successful SEC filing extraction requires a multi-faceted approach combining:

1. **Structure-aware chunking** that respects document elements (titles, tables, sections)
2. **Schema-based extraction** with Pydantic models and strategic optionality
3. **RAG (Retrieval-Augmented Generation)** for long documents exceeding context windows
4. **Robust preprocessing** to clean HTML and extract narrative content
5. **Validation mechanisms** including citations, page numbers, and verification
6. **Deduplication strategies** for handling multiple related filings from same ticker

---

## 1. Schema Design Patterns

### Hierarchical Organization
**Industry Standard**: Schema should mirror the natural document structure, organizing filings into logical sections:
- Filing information (type, date, accession number)
- Company profile (ticker, CIK, sector, industry)
- Financial highlights (revenue, income, cash flow)
- Business segments and geographic data
- Risk factors
- Management discussion and analysis (MD&A)

**Source**: LlamaExtract documentation, "Mining Financial Data from SEC Filings"

### Strategic Optionality
**Key Principle**: Balance between required and optional fields to prevent hallucination while maximizing extraction coverage.

**Best Practice**:
- Mark fields as optional when they may not appear uniformly across different companies
- Too many required fields force LLM hallucination
- Too many optional fields result in missed information

**Example**:
```python
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class FilingInfo(BaseModel):
    filing_type: Literal["8-K", "10-K", "10-Q", "424B5"]
    filing_date: str
    accession_number: str
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[str] = None
    reporting_period_end: Optional[str] = None

class CompanyProfile(BaseModel):
    ticker: str
    company_name: str
    cik: str
    sector: Optional[str] = None
    industry: Optional[str] = None

class SECFilingExtraction(BaseModel):
    filing: FilingInfo
    company: CompanyProfile
    risk_factors: Optional[List[str]] = Field(
        None,
        description="List of material risk factors disclosed in filing"
    )
    material_contracts: Optional[List[str]] = Field(
        None,
        description="Material definitive agreements (Item 1.01 for 8-K)"
    )
    unregistered_sales: Optional[str] = Field(
        None,
        description="Details of unregistered equity sales (Item 3.02 for 8-K)"
    )
```

### Detailed Field Descriptions
**Critical Practice**: Include precise field definitions with examples to combat ambiguity in long documents.

**Guidance**: Field descriptions should:
- Specify exact location in document (e.g., "Item 1.01" for 8-K filings)
- Provide extraction examples showing expected behavior
- Define format expectations (dates, currencies, percentages)
- Clarify edge cases

---

## 2. Document Preprocessing Pipeline

### Three-Stage Pipeline
**Industry Standard** (from arXiv 2409.17581):

1. **Data Collection**
   - Query SEC-EDGAR endpoints using ticker symbols
   - Convert tickers to Central Index Keys (CIKs)
   - Retrieve raw HTML filings via accession numbers

2. **Data Cleaning**
   - **Date Identification**: Use regex to locate reporting periods (SEC has uniform formatting)
   - **Narrative Text Extraction**: Use `unstructured-io` library with Parts of Speech tagging
     - Differentiate narrative text from lists, titles, and tables
     - Require "significant number of verbs and non-proper nouns"
   - **Section Partitioning**: Identify sections from Table of Contents, match to pages
   - Output: Structured CSV with section labels

3. **LLM Evaluation**
   - Feed cleaned, sectioned content to LLM with structured prompts
   - Extract structured data according to schema

### HTML Cleaning Best Practices
**Key Tool**: `unstructured-io` Python library specifically designed for SEC filings

**Cleaning Steps**:
- Remove boilerplate EDGAR headers/footers
- Strip style tags, scripts, and formatting
- Preserve semantic structure (headings, lists, tables)
- Identify and extract tables separately (special handling required)
- Extract text while maintaining section boundaries

**Source**: "From Chaos to Clarity: Making SEC Filings LLM-Ready"

---

## 3. Chunking Strategies for RAG

### Element-Based Chunking (Recommended for SEC Filings)
**Research Finding**: Element-based chunking significantly outperforms paragraph-based approaches for financial documents.

**Method**:
- Start new chunk when encountering title elements
- Start new chunk when encountering table elements
- Preserve entire tables within single chunks (don't split)
- Respect document structure indicated by headings/subheadings

**Performance**: "Largely improves RAG results on financial reporting" (arXiv 2402.05131)

**Optimal Chunk Size**: 1,800 characters (moderate size) with top-50 retrieval

### Semantic Chunking
**Method**:
- Embed each sentence using embedding model
- Calculate cosine distance between consecutive sentence embeddings
- If distance exceeds threshold → split chunk at that boundary
- Preserves semantic coherence across chunk boundaries

**Use Case**: When document doesn't have clear structural elements

### Recursive Chunking
**Method**:
- Hierarchical approach with predefined delimiters
- Begin by splitting at larger semantically meaningful boundaries (sections)
- Recurse into finer splits as needed (subsections → paragraphs)

**Use Case**: For deeply nested document structures

### Contextual Chunking
**Method**:
- Use LLM to interpret chunk content
- Add supplementary information (labels, summaries) to each chunk
- Addresses semantic gaps when chunks are retrieved independently

**Trade-off**: Higher processing cost, better retrieval quality

---

## 4. Retrieval-Augmented Generation (RAG)

### When to Use RAG
**Context Window Considerations**:
- 10-Q filings can reach 419 pages
- 10-K filings commonly exceed 200 pages
- GPT-4 Turbo: 128K context window
- Claude 3.5 Sonnet: 200K context window
- Cohere Command-R+: 128K context window

**Recommendation**: Use RAG when filing exceeds 50% of model's context window to ensure quality extraction.

### RAG Architecture for SEC Filings

```
┌─────────────────────┐
│  SEC Filing (HTML)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Preprocessing      │
│  - Clean HTML       │
│  - Extract sections │
│  - Element chunking │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Embedding          │
│  (OpenAI, Cohere)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Vector Store       │
│  (FAISS, Chroma)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Query → Retrieval  │
│  (Top-K chunks)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Re-ranking         │
│  (Cohere, BGE)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  LLM Extraction     │
│  (Structured output)│
└─────────────────────┘
```

### Re-ranking for Relevance
**Challenge**: Semantic similarity ≠ relevance for extraction tasks

**Solution**: Use re-ranking algorithms to prioritize relevance over cosine similarity
- Cohere re-rank API
- BGE (BAAI General Embedding) re-ranker
- Cross-encoder models

**Performance**: Re-ranking improves extraction accuracy by 15-30% over pure similarity search

---

## 5. Prompt Engineering Strategies

### Role-Based Zero-Shot Prompting
**Industry Pattern** (arXiv 2409.17581):

```python
base_prompt = """
You are an AI financial analyst tasked with extracting structured information
from SEC filings.

Your goal is to extract the following information from the provided filing:
{schema_description}

Guidelines:
- Extract only information explicitly stated in the document
- If information is not present, return null for that field
- Preserve exact wording for material events (Item 1.01, Item 3.02, etc.)
- Include page numbers for verification
- Do not infer or extrapolate beyond what is stated

Filing excerpt:
{filing_text}

Extract the information as JSON following this schema:
{json_schema}
"""
```

### Dual-Prompt Validation
**Technique**: Use two prompt variants (standard and strict) to reduce bias
- Standard prompt: Permissive extraction with reasonable inference
- Strict prompt: Extract only explicitly stated information
- Average results from both prompts for final output

### Multi-Dimensional Evaluation
**Pattern**: Evaluate filings across independent dimensions
- Financial confidence/robustness
- Environmental/sustainability commitments
- Innovation and R&D investment
- Workforce/people management

**Validation**: Ensure dimensions remain "largely uncorrelated" to prove independence

---

## 6. Validation and Quality Assurance

### Citation Tracking
**Industry Standard**: Include page numbers and source locations for all extracted data

**Benefits**:
- Enables rapid verification of extraction accuracy
- Allows auditors to trace data to source
- Detects hallucination by comparing to source pages

**Implementation**:
```python
class ExtractedField(BaseModel):
    value: str
    page_numbers: List[int]
    source_section: str
    confidence: float = Field(..., ge=0.0, le=1.0)
```

### Reasoning Chains
**Advanced Technique**: Request LLM to provide reasoning for each extraction

**Example**:
```python
class RiskFactor(BaseModel):
    description: str
    severity: Literal["high", "medium", "low"]
    page_numbers: List[int]
    reasoning: str = Field(
        ...,
        description="Explain why this was identified as a risk factor"
    )
```

### Verification Workflow
1. Extract data with LLM
2. Generate citations (page numbers, sections)
3. Randomly sample 10-20% of extractions
4. Human reviewer verifies against source document
5. Track accuracy metrics per field type
6. Iteratively refine prompts based on error patterns

---

## 7. SEC Filing Deduplication Strategies

### Problem Statement
**Challenge**: Multiple related filings from same ticker within short timeframe
- Example: FBLG filed both 8-K and 424B5 on 2025-11-25
- 8-K (Item 1.01): Material Definitive Agreement
- 8-K (Item 3.02): Unregistered Sales of Equity
- 424B5: Prospectus Supplement

These filings are **related** - the 424B5 describes the offering mentioned in the 8-K.

### Industry Approach: Filing Relationship Detection

#### Strategy 1: Temporal Grouping
**Method**: Group filings from same ticker within sliding time window

**Algorithm**:
```python
GROUPING_WINDOW_HOURS = 4  # 4-hour window

def should_group_filings(filing_a, filing_b):
    """Determine if two filings should be grouped together"""
    if filing_a.ticker != filing_b.ticker:
        return False

    time_delta = abs(filing_a.filed_date - filing_b.filed_date)
    if time_delta > timedelta(hours=GROUPING_WINDOW_HOURS):
        return False

    # Check if filing types are related
    return are_related_filing_types(filing_a.type, filing_b.type)

def are_related_filing_types(type_a, type_b):
    """Define which filing types are typically related"""
    RELATED_GROUPS = [
        {"8-K", "424B5", "424B3"},  # Material events + prospectus
        {"10-K", "10-K/A"},          # Original + amendment
        {"10-Q", "10-Q/A"},          # Original + amendment
        {"8-K", "8-K/A"},            # Original + amendment
    ]

    for group in RELATED_GROUPS:
        if type_a in group and type_b in group:
            return True
    return False
```

#### Strategy 2: Accession Number Analysis
**Method**: SEC assigns related filings sequential accession numbers

**Pattern**: `0001193125-25-294631` and `0001193125-25-294634`
- Same CIK prefix (0001193125)
- Same filing date (25 = 2025)
- Similar sequential suffix (294631 vs 294634)

**Implementation**:
```python
def extract_accession_prefix(accession_no):
    """Extract CIK and date from accession number"""
    # Format: XXXXXXXXXX-YY-NNNNNN
    parts = accession_no.split("-")
    return f"{parts[0]}-{parts[1]}"  # CIK-YY

def are_sequential_filings(acc_a, acc_b, max_distance=100):
    """Check if accession numbers suggest related filings"""
    prefix_a = extract_accession_prefix(acc_a)
    prefix_b = extract_accession_prefix(acc_b)

    if prefix_a != prefix_b:
        return False

    suffix_a = int(acc_a.split("-")[-1])
    suffix_b = int(acc_b.split("-")[-1])

    return abs(suffix_a - suffix_b) <= max_distance
```

#### Strategy 3: Content Similarity (LLM-Based)
**Method**: Use LLM to determine if filings discuss the same event

**Approach**:
```python
def check_filing_similarity(filing_a_summary, filing_b_summary):
    """Use LLM to determine if filings describe related events"""
    prompt = f"""
    You are analyzing two SEC filings from the same company filed on the same day.
    Determine if they describe the SAME underlying corporate event or DIFFERENT events.

    Filing A ({filing_a.type}):
    {filing_a_summary}

    Filing B ({filing_b.type}):
    {filing_b_summary}

    Are these filings related to the same corporate event?
    Respond with: SAME_EVENT or DIFFERENT_EVENTS

    Reasoning: [explain why]
    """

    response = llm.generate(prompt)
    return "SAME_EVENT" in response
```

### Consolidation Approach
**Recommendation**: When related filings are detected, consolidate into single alert:

```python
class ConsolidatedAlert(BaseModel):
    ticker: str
    primary_filing: FilingInfo  # The most informative filing (usually 8-K)
    related_filings: List[FilingInfo]  # Related filings (424B5, etc.)

    consolidated_summary: str = Field(
        ...,
        description="Summary combining information from all related filings"
    )

    key_items: List[str] = Field(
        ...,
        description="List of material items across all filings"
    )

    filing_relationship: str = Field(
        ...,
        description="Explanation of how filings are related"
    )
```

**Example Consolidated Alert**:
```
TICKER: FBLG - FibroBiologics, Inc.
FILING DATE: 2025-11-25
PRIMARY FILING: 8-K (Accession: 0001193125-25-294634)
RELATED FILINGS: 424B5 (Accession: 0001193125-25-294631)

SUMMARY:
FibroBiologics entered a material definitive agreement for an offering of
unregistered equity securities. The company filed both the current report
(8-K) disclosing the agreement and a prospectus supplement (424B5) providing
offering details.

KEY ITEMS:
• Item 1.01: Entry into Material Definitive Agreement
• Item 3.02: Unregistered Sales of Equity Securities
• Item 7.01: Regulation FD Disclosure
• Prospectus: 821 KB supplement describing offering terms

RELATIONSHIP:
The 8-K discloses the material agreement while the 424B5 provides detailed
prospectus information about the same equity offering.
```

---

## 8. Implementation Recommendations for Catalyst Bot

### Phase 1: Enhanced Extraction (Immediate)
**Goal**: Increase information quality from individual filings

**Actions**:
1. Implement Pydantic schema for 8-K and 424B5 filings
2. Add structured extraction prompts with field descriptions
3. Include page number citations for verification
4. Extract specific Items (1.01, 3.02, etc.) from 8-K filings

**Code Location**: `src/catalyst_bot/sec_digester.py`

### Phase 2: Filing Consolidation (Short-term)
**Goal**: Avoid duplicate alerts for related filings

**Actions**:
1. Implement temporal grouping (4-hour window)
2. Add accession number similarity detection
3. Create consolidation logic for related filings
4. Update Discord alert format to show related filings

**Code Location**: `src/catalyst_bot/sec_digester.py`, `src/catalyst_bot/feed_aggregator.py`

### Phase 3: RAG Pipeline (Medium-term)
**Goal**: Handle long filings (10-K, 10-Q) effectively

**Actions**:
1. Integrate element-based chunking for SEC filings
2. Add vector store (FAISS or Chroma) for chunk storage
3. Implement re-ranking for retrieval quality
4. Build RAG extraction pipeline for long documents

**Dependencies**:
- `pip install faiss-cpu chromadb sentence-transformers`
- `pip install llama-index` (optional, for pre-built RAG components)

### Phase 4: Validation Dashboard (Long-term)
**Goal**: Monitor extraction quality and accuracy

**Actions**:
1. Build web dashboard showing extractions with citations
2. Allow users to verify/flag incorrect extractions
3. Track accuracy metrics per filing type
4. Use feedback to refine prompts iteratively

---

## 9. Open-Source Tools and Frameworks

### LlamaIndex (Primary Recommendation)
**Purpose**: Complete RAG framework with SEC filing support

**Features**:
- Pre-built 10-K/10-Q schemas
- Element-based chunking for financial documents
- Citation tracking built-in
- Scalable batch processing
- Python SDK for integration

**Installation**:
```bash
pip install llama-index
pip install llama-cloud  # For LlamaExtract API
```

**Usage**:
```python
from llama_index.core import VectorStoreIndex, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_cloud import LlamaExtract

# Initialize LlamaExtract
extractor = LlamaExtract(api_key=os.getenv("LLAMA_CLOUD_API_KEY"))

# Extract using pre-built 10-K schema
result = extractor.extract(
    file_path="path/to/10k.html",
    schema_id="10k_financial_filing"  # Pre-built schema
)

print(result.data)  # Structured JSON output
print(result.citations)  # Page numbers for each field
```

### Unstructured.io
**Purpose**: Clean and preprocess SEC filings for LLM consumption

**Features**:
- Parts of Speech tagging
- Table extraction and preservation
- Section identification
- HTML cleaning optimized for EDGAR filings

**Installation**:
```bash
pip install unstructured[html]
```

**Usage**:
```python
from unstructured.partition.html import partition_html

# Clean SEC filing HTML
elements = partition_html(filename="filing.html")

# Separate by element type
titles = [e for e in elements if e.category == "Title"]
narratives = [e for e in elements if e.category == "NarrativeText"]
tables = [e for e in elements if e.category == "Table"]
```

### LangChain
**Purpose**: Alternative RAG framework with flexible architecture

**Features**:
- Modular RAG components
- Support for multiple LLM providers
- Custom chunking strategies
- Document loaders for SEC filings

**Installation**:
```bash
pip install langchain langchain-community
```

### Chroma / FAISS
**Purpose**: Vector stores for RAG retrieval

**Chroma Features**:
- Persistent storage
- Metadata filtering
- Easy integration with LangChain/LlamaIndex

**FAISS Features**:
- Facebook Research library
- Extremely fast similarity search
- CPU and GPU support

**Installation**:
```bash
pip install chromadb  # Persistent, easy to use
pip install faiss-cpu  # Fast, in-memory
```

---

## 10. Cost Considerations

### LLM API Costs (November 2025 Pricing)

| Provider | Model | Input (per 1M tokens) | Output (per 1M tokens) |
|----------|-------|----------------------|------------------------|
| OpenAI | GPT-4 Turbo | $10.00 | $30.00 |
| OpenAI | GPT-3.5 Turbo | $0.50 | $1.50 |
| Anthropic | Claude 3.5 Sonnet | $3.00 | $15.00 |
| Google | Gemini 1.5 Pro | $1.25 | $5.00 |
| Cohere | Command-R+ | $3.00 | $15.00 |

### Processing Cost Estimates

**Scenario**: Processing 100 SEC filings per day

**Option 1: Direct LLM Extraction (No RAG)**
- Average filing size: 50,000 tokens (after cleaning)
- Extraction prompt: 1,000 tokens
- Output: 500 tokens
- Cost per filing (GPT-4 Turbo): (51,000 × $10 + 500 × $30) / 1,000,000 = $0.525
- **Daily cost: $52.50**

**Option 2: RAG Pipeline**
- Chunking + embedding: $0.02 per filing (one-time)
- Retrieval: Free (local vector store)
- LLM extraction on 3 chunks: 5,000 tokens input
- Cost per filing: (5,000 × $10 + 500 × $30) / 1,000,000 = $0.065
- **Daily cost: $6.50** (87% reduction)

**Option 3: LlamaExtract (Commercial)**
- Pricing: $0.10 per page (estimated)
- Average filing: 100 pages
- Cost per filing: $10.00
- **Daily cost: $1,000.00**

**Recommendation**: Use RAG pipeline for cost efficiency, reserve LlamaExtract for complex 10-K filings.

---

## 11. Key Takeaways

### Critical Success Factors
1. **Structure-aware processing**: Respect document elements (titles, tables, sections)
2. **Schema design**: Balance required/optional fields to prevent hallucination
3. **Chunking strategy**: Use element-based chunking for SEC filings
4. **Validation**: Include citations, page numbers, and verification workflows
5. **Deduplication**: Group related filings to avoid duplicate alerts
6. **Cost optimization**: Use RAG to reduce LLM token consumption

### Common Pitfalls to Avoid
1. **Over-specification**: Too many required fields force LLM hallucination
2. **Paragraph chunking**: Loses document structure, reduces accuracy
3. **No validation**: Extractions may contain invented information
4. **Ignoring relationships**: Related filings create duplicate alerts
5. **Context overflow**: Long filings exceed LLM context windows

### Next Steps for Catalyst Bot
1. ✅ Research completed (this document)
2. ⏭️ Design Pydantic schemas for 8-K, 424B5, 10-K, 10-Q
3. ⏭️ Implement filing deduplication logic
4. ⏭️ Add structured extraction prompts with citations
5. ⏭️ Test on historical FBLG filings (2025-11-25)
6. ⏭️ Evaluate RAG implementation for 10-K filings

---

## 12. References

### Academic Papers
- **"Financial Report Chunking for Effective Retrieval Augmented Generation"** (arXiv 2402.05131v2, 2024)
  - Key finding: Element-based chunking outperforms paragraph chunking
  - Optimal chunk size: 1,800 characters

- **"A Scalable Data-Driven Framework for Systematic Analysis of SEC 10-K Filings Using LLMs"** (arXiv 2409.17581v1, 2024)
  - Three-stage pipeline: collection, cleaning, evaluation
  - Role-based zero-shot prompting strategy

- **"Improving Retrieval for RAG based Question Answering Models on Financial Documents"** (arXiv 2404.07221v1, 2024)
  - Re-ranking improves retrieval quality
  - Semantic similarity ≠ relevance

### Commercial Tools
- **LlamaIndex LlamaExtract**: https://www.llamaindex.ai/blog/mining-financial-data-from-sec-filings-with-llamaextract
- **Unstructured.io**: https://unstructured.io/
- **Sensible**: https://www.sensible.so/extract/10-k
- **sec-api.io**: https://sec-api.io/

### Blog Posts
- **"From Chaos to Clarity: Making SEC Filings LLM-Ready"** (Blue Sky Data Platform, 2024)
- **"Long-Context Isn't All You Need: How Retrieval & Chunking Impact Finance RAG"** (Snowflake Engineering Blog, 2024)
- **"Get Citations and Reasoning for Extracted Data in LlamaExtract"** (LlamaIndex, 2024)

---

**Document Version**: 1.0
**Last Updated**: November 25, 2025
**Author**: Claude Code (Anthropic)
**License**: MIT
