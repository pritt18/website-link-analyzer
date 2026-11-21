from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class LinkAnalysisRequest(BaseModel):
    """Payload for submitting a website URL for comprehensive intelligence analysis."""
    url: str = Field(
        ...,
        description="Valid public website URL (must include http:// or https://)",
        examples=["https://stripe.com"]
    )


# ============================================================================
# Section 1: Competitor vs Your Brand Details
# ============================================================================

class CompetitorItem(BaseModel):
    """Detailed competitor profile and direct comparison fields."""
    name: str = Field(..., description="Competitor brand or company name")
    main_service: str = Field(..., description="Core service or primary product offering")
    target_market: str = Field(..., description="Target audience or industry focus")
    key_strengths: str = Field(..., description="Key competitive advantage or market strength")
    weaknesses_or_gaps: str = Field(..., description="Observed weaknesses, blindspots, or market gaps")
    opportunity: str = Field(..., description="Strategic opportunity for your brand against this competitor")


class CompetitorAnalysis(BaseModel):
    """Section 1: Brand positioning and competitor landscape analysis."""
    brand_overview: str = Field(..., description="Executive summary of the brand's market positioning")
    competitors: List[CompetitorItem] = Field(
        ...,
        min_length=3,
        description="Identified competitors (minimum 3 credible competitors)"
    )
    strengths: List[str] = Field(
        ...,
        description="Your brand's distinctive competitive advantages"
    )
    opportunities: List[str] = Field(
        ...,
        description="Actionable strategic opportunities to improve market positioning"
    )


# ============================================================================
# Section 2: Top 5 Target Search Queries
# ============================================================================

class TargetSearchQuery(BaseModel):
    """Section 2: High-intent cross-platform discovery search query."""
    query: str = Field(..., description="Target search query or phrase")
    platforms: List[str] = Field(
        ...,
        description="Platforms where this query is relevant (Google, LinkedIn, Facebook, Instagram, X)"
    )
    intent: str = Field(
        ...,
        description="Search intent (e.g. Service Discovery, B2B Search, Inspiration, Commercial Investigation)"
    )
    business_relevance: str = Field(..., description="Why this query matters to the business")
    target_audience: str = Field(..., description="Audience persona conducting this search")


# ============================================================================
# Section 3: SEO Improvement
# ============================================================================

class SEOImprovements(BaseModel):
    """Section 3: On-page SEO recommendations, metadata, and content strategy."""
    primary_keyword: str = Field(..., description="Highest-volume core target keyword")
    secondary_keywords: List[str] = Field(..., description="Related commercial & thematic keywords")
    long_tail_keywords: List[str] = Field(
        default_factory=list,
        description="High-intent conversational/long-tail search phrases"
    )
    recommended_title: str = Field(
        ...,
        description="Optimized title tag (incorporating primary keyword under 60 chars)"
    )
    meta_description: str = Field(
        ...,
        description="High-converting meta description (under 160 chars)"
    )
    supporting_content: List[str] = Field(
        ...,
        description="Strategic content expansion ideas (landing pages, FAQs, topic clusters)"
    )


# ============================================================================
# Section 4: Top 5 Services
# ============================================================================

class TopService(BaseModel):
    """Section 4: Key service offering derived from website analysis."""
    service_name: str = Field(..., description="Official title or name of the service")
    description: str = Field(..., description="Clear explanation of the service capability")
    target_industry: str = Field(..., description="Primary vertical or industry served")
    target_customer: str = Field(..., description="Ideal customer persona or buyer role")
    main_benefit: str = Field(..., description="Core value proposition and expected outcome")
    source: str = Field(
        default="extracted_from_content",
        description="Indicates whether service is extracted_from_content or inferred_recommendation"
    )


# ============================================================================
# Section 5: Target Audience Identification
# ============================================================================

class TargetAudience(BaseModel):
    """Section 5: Customer segmentation, personas, and behavioral requirements."""
    primary_audience: List[str] = Field(..., description="Core target decision-makers and buyers")
    secondary_audience: List[str] = Field(..., description="Influencers, evaluators, or secondary users")
    industries: List[str] = Field(..., description="Priority industry verticals")
    business_types: List[str] = Field(
        default_factory=list,
        description="Types of businesses (e.g. Early-stage Startups, Mid-market B2B, Enterprise)"
    )
    customer_profiles: List[str] = Field(
        default_factory=list,
        description="Representative buyer personas and job titles"
    )
    geographical_focus: Optional[str] = Field(
        default=None,
        description="Geographical focus or market territory (e.g. Global, North America, India)"
    )
    customer_needs: List[str] = Field(..., description="Core customer pain points, challenges, and requirements")
    customer_interests: List[str] = Field(
        default_factory=list,
        description="Key interests, topical affinities, and tech adoption preferences"
    )
    recommended_segments: List[str] = Field(
        default_factory=list,
        description="Recommended marketing and outreach segmentation tiers"
    )


# ============================================================================
# Top-Level Aggregated Response Schemas
# ============================================================================

class BrandInfo(BaseModel):
    """Extracted identity and brand overview."""
    name: str = Field(..., description="Identified brand or trading entity name")
    category: str = Field(..., description="Primary business category / classification")
    summary: str = Field(..., description="Concise synopsis of company business operations")


class AnalysisResult(BaseModel):
    """Five-pillar structured intelligence breakdown."""
    competitor_analysis: CompetitorAnalysis
    target_search_queries: List[TargetSearchQuery]
    seo_improvements: SEOImprovements
    top_services: List[TopService]
    target_audience: TargetAudience


class AnalysisMetadata(BaseModel):
    """Operational telemetry and processing metadata."""
    duration_seconds: float
    model_provider: str
    model_name: str
    extracted_text_length: int


class LinkAnalysisResponse(BaseModel):
    """Full structured response for POST /link-analysis."""
    success: bool = True
    website: str
    brand: BrandInfo
    analysis: AnalysisResult
    metadata: Optional[AnalysisMetadata] = None


class ErrorResponse(BaseModel):
    """Standardized error structure."""
    success: bool = False
    detail: str
    error_code: str
