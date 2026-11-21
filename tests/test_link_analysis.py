import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.schemas import LinkAnalysisResponse
from app.services.analysis_service import AnalysisService
from app.services.competitor_service import CompetitorService
from app.services.llm_service import MockLLMService, _clean_json_response
from app.services.website_extractor import WebsiteExtractor, WebsiteContentEmptyError
from app.utils.validators import (
    validate_url_security,
    SSRFValidationError,
    InvalidURLError,
)


# ============================================================================
# 1. URL & SSRF Validation Tests
# ============================================================================

def test_valid_urls_allowed():
    """Verify standard legitimate public URLs pass without error."""
    valid_urls = [
        "https://example.com",
        "http://example.com",
        "https://github.com/fastapi/fastapi",
        "example.com"  # auto-prepends https://
    ]
    for u in valid_urls:
        clean_url, _ = validate_url_security(u, block_private=False)
        assert clean_url.startswith("http")


def test_invalid_scheme_rejected():
    """Verify non-HTTP protocols (file, ftp, javascript) are rejected."""
    invalid_protocols = [
        "file:///etc/passwd",
        "ftp://ftp.example.com",
        "gopher://gopher.floodgap.com",
        "javascript:alert(1)"
    ]
    for u in invalid_protocols:
        with pytest.raises(InvalidURLError):
            validate_url_security(u)


def test_ssrf_loopback_blocked():
    """Verify loopback addresses are blocked by SSRF protection."""
    loopback_targets = [
        "http://localhost:8000",
        "http://127.0.0.1:4000",
        "http://127.0.0.2",
        "http://0.0.0.0"
    ]
    for target in loopback_targets:
        with pytest.raises(SSRFValidationError):
            validate_url_security(target, block_private=True)


def test_ssrf_cloud_metadata_blocked():
    """Verify AWS/GCP/Azure link-local metadata IP 169.254.169.254 is strictly blocked."""
    metadata_targets = [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254"
    ]
    for target in metadata_targets:
        with pytest.raises(SSRFValidationError):
            validate_url_security(target, block_private=True)


def test_ssrf_private_network_blocked():
    """Verify private RFC1918 subnets (10.x, 172.16.x, 192.168.x) are blocked."""
    private_targets = [
        "http://10.0.0.1/admin",
        "http://172.16.0.1",
        "http://192.168.1.100"
    ]
    for target in private_targets:
        with pytest.raises(SSRFValidationError):
            validate_url_security(target, block_private=True)


# ============================================================================
# 2. HTML Parsing & Website Extractor Tests
# ============================================================================

def test_html_parsing_logic(mock_html_content):
    """Verify DOM extraction correctly harvests title, meta, headings, nav, and body."""
    extractor = WebsiteExtractor()
    data = extractor._parse_html(
        requested_url="https://acmecloud.example.com",
        final_url="https://acmecloud.example.com",
        status_code=200,
        html=mock_html_content
    )

    assert "Acme Cloud Solutions" in data.title
    assert "Acme Cloud delivers resilient" in data.meta_description
    assert "kubernetes" in data.meta_keywords
    assert "Modern Cloud Infrastructure Designed for Scale" in data.headings["h1"]
    assert len(data.headings["h2"]) == 3
    assert "Managed Kubernetes" in data.nav_links
    assert len(data.clean_text) > 100
    assert "<script>" not in data.clean_text
    assert "<style>" not in data.clean_text


def test_empty_content_raises_error():
    """Verify empty or non-informative HTML triggers WebsiteContentEmptyError."""
    extractor = WebsiteExtractor()
    with pytest.raises(WebsiteContentEmptyError):
        extractor._parse_html("https://empty.com", "https://empty.com", 200, "<html><body> </body></html>")


# ============================================================================
# 3. LLM Service & Schema Tests
# ============================================================================

@pytest.mark.asyncio
async def test_mock_llm_service(mock_extracted_data):
    """Verify MockLLMService produces valid 5-pillar schema conforming output."""
    service = MockLLMService()
    brand, analysis = await service.analyze_website(mock_extracted_data)

    assert brand.name != ""
    assert brand.category != ""
    assert brand.summary != ""

    # Section 1: Competitor analysis
    assert len(analysis.competitor_analysis.competitors) >= 3
    assert len(analysis.competitor_analysis.strengths) >= 2
    assert len(analysis.competitor_analysis.opportunities) >= 2

    # Section 2: Top 5 Target Search Queries
    assert len(analysis.target_search_queries) == 5
    for q in analysis.target_search_queries:
        assert q.query != ""
        assert len(q.platforms) >= 1
        assert q.intent != ""
        assert q.business_relevance != ""
        assert q.target_audience != ""

    # Section 3: SEO Improvements
    assert analysis.seo_improvements.primary_keyword != ""
    assert len(analysis.seo_improvements.secondary_keywords) >= 2
    assert analysis.seo_improvements.recommended_title != ""
    assert analysis.seo_improvements.meta_description != ""
    assert len(analysis.seo_improvements.supporting_content) >= 2

    # Section 4: Top 5 Services
    assert len(analysis.top_services) == 5
    for s in analysis.top_services:
        assert s.service_name != ""
        assert s.description != ""
        assert s.target_industry != ""
        assert s.target_customer != ""
        assert s.main_benefit != ""
        assert s.source in ("extracted_from_content", "inferred_recommendation")

    # Section 5: Target Audience
    assert len(analysis.target_audience.primary_audience) >= 1
    assert len(analysis.target_audience.industries) >= 1
    assert len(analysis.target_audience.customer_needs) >= 1


def test_clean_json_response_helper():
    """Verify markdown code fences and JSON string cleaning helper."""
    raw_markdown = '```json\n{"brand": {"name": "TestCorp", "category": "Tech", "summary": "Sample"}}\n```'
    parsed = _clean_json_response(raw_markdown)
    assert parsed["brand"]["name"] == "TestCorp"

    raw_plain = '   {"brand": {"name": "PlainCorp"}}   '
    parsed_plain = _clean_json_response(raw_plain)
    assert parsed_plain["brand"]["name"] == "PlainCorp"


# ============================================================================
# 4. End-to-End API Integration Tests
# ============================================================================

def test_health_check_endpoint(client):
    """GET /health should return 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "llm_provider" in data


def test_root_endpoint(client):
    """GET / should return 200 with service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "/docs" in data["docs_url"]


def test_post_link_analysis_success(client, mock_extracted_data):
    """POST /link-analysis should return 200 and complete 5-section response."""
    with patch.object(
        WebsiteExtractor, "fetch_and_extract", new=AsyncMock(return_value=mock_extracted_data)
    ):
        payload = {"url": "https://acmecloud.example.com"}
        response = client.post("/link-analysis", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["website"] == "https://acmecloud.example.com"
        assert "brand" in data
        assert "analysis" in data
        
        analysis = data["analysis"]
        # Section 1
        assert "competitor_analysis" in analysis
        assert len(analysis["competitor_analysis"]["competitors"]) >= 3
        
        # Section 2
        assert "target_search_queries" in analysis
        assert len(analysis["target_search_queries"]) == 5
        
        # Section 3
        assert "seo_improvements" in analysis
        assert analysis["seo_improvements"]["primary_keyword"] != ""
        
        # Section 4
        assert "top_services" in analysis
        assert len(analysis["top_services"]) == 5
        
        # Section 5
        assert "target_audience" in analysis
        assert len(analysis["target_audience"]["primary_audience"]) >= 1


def test_post_link_analysis_ssrf_blocked(client):
    """POST /link-analysis targeting loopback/internal IP must return 400 Bad Request."""
    payload = {"url": "http://127.0.0.1:8080/admin"}
    response = client.post("/link-analysis", json=payload)
    
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "SSRF_SECURITY_VIOLATION"


def test_post_link_analysis_invalid_scheme(client):
    """POST /link-analysis with invalid protocol scheme must return 400 Bad Request."""
    payload = {"url": "ftp://files.example.com"}
    response = client.post("/link-analysis", json=payload)
    
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "INVALID_URL_FORMAT"
