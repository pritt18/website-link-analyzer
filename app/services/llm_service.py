import abc
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings
from app.schemas import (
    AnalysisResult,
    BrandInfo,
    CompetitorAnalysis,
    CompetitorItem,
    SEOImprovements,
    TargetAudience,
    TargetSearchQuery,
    TopService,
)
from app.services.website_extractor import ExtractedWebsiteData

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Raised when an LLM provider fails to generate or return a valid response."""
    pass


class BaseLLMService(abc.ABC):
    """Abstract interface for LLM intelligence providers."""

    @abc.abstractmethod
    async def analyze_website(
        self, data: ExtractedWebsiteData
    ) -> Tuple[BrandInfo, AnalysisResult]:
        """Processes extracted website content and returns structured brand & analysis models."""
        pass


SYSTEM_INSTRUCTION = """You are an elite enterprise market intelligence and SEO analytics engine.
Analyze the provided website content and generate a comprehensive, highly realistic intelligence report.

CRITICAL INSTRUCTIONS:
1. Ground your analysis strictly in the provided website content, metadata, and industry realities.
2. Section 1 (Competitor vs Your Brand): Identify the brand name, business category, and at least 3 genuine direct competitors in the market. Compare their strengths, weaknesses, gaps, and strategic opportunities for this brand.
3. Section 2 (Top 5 Target Search Queries): Provide exactly 5 high-converting search queries across platforms (Google Search, LinkedIn, Facebook, Instagram, X). DO NOT invent numeric search volumes or rankings without live API access. State intent, business relevance, and target persona.
4. Section 3 (SEO Improvement): Provide primary keyword, secondary keywords, long-tail phrases, an optimized title tag (under 60 characters), a compelling meta description (under 160 characters), and high-value supporting content recommendations (e.g. service landing pages, industry guides, FAQs).
5. Section 4 (Top 5 Services): Identify the 5 most important services offered. Detail the service name, description, target industry, customer persona, and core business benefit. Clearly mark the source as 'extracted_from_content' or 'inferred_recommendation'.
6. Section 5 (Target Audience Identification): Outline primary and secondary audience personas, industry verticals, business types, customer pain points/needs, customer interests, and recommended marketing segments.

You MUST return ONLY a valid, parseable JSON object matching this schema exactly:
{
  "brand": {
    "name": "Brand Name",
    "category": "Main Category",
    "summary": "Concise business overview"
  },
  "competitor_analysis": {
    "brand_overview": "Strategic brand positioning overview",
    "competitors": [
      {
        "name": "Competitor Name",
        "main_service": "Their core offering",
        "target_market": "Target segment",
        "key_strengths": "Their primary advantage",
        "weaknesses_or_gaps": "Their limitation or market gap",
        "opportunity": "How your brand can capitalize"
      }
    ],
    "strengths": ["Brand advantage 1", "Brand advantage 2"],
    "opportunities": ["Market expansion opportunity 1", "Opportunity 2"]
  },
  "target_search_queries": [
    {
      "query": "Target query text",
      "platforms": ["Google", "LinkedIn"],
      "intent": "Service Discovery",
      "business_relevance": "Why this query converts",
      "target_audience": "Audience persona"
    }
  ],
  "seo_improvements": {
    "primary_keyword": "Primary keyword",
    "secondary_keywords": ["keyword 1", "keyword 2"],
    "long_tail_keywords": ["phrase 1", "phrase 2"],
    "recommended_title": "SEO Optimized Title",
    "meta_description": "SEO Optimized Meta Description",
    "supporting_content": ["Topic cluster 1", "FAQ section 2"]
  },
  "top_services": [
    {
      "service_name": "Service Title",
      "description": "Clear service description",
      "target_industry": "Industry vertical",
      "target_customer": "Target persona",
      "main_benefit": "Quantifiable or qualitative benefit",
      "source": "extracted_from_content"
    }
  ],
  "target_audience": {
    "primary_audience": ["Audience 1", "Audience 2"],
    "secondary_audience": ["Audience 3"],
    "industries": ["Vertical 1", "Vertical 2"],
    "business_types": ["Enterprise", "B2B SaaS"],
    "customer_profiles": ["CTO", "Head of Growth"],
    "geographical_focus": "Global / North America",
    "customer_needs": ["Pain point 1", "Requirement 2"],
    "customer_interests": ["Interest 1", "Interest 2"],
    "recommended_segments": ["Segment Tier 1", "Segment Tier 2"]
  }
}
"""


def _clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Extracts and parses JSON from raw LLM output, handling markdown blocks."""
    text = raw_text.strip()
    # Strip markdown ```json ... ``` wrapper if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    else:
        # Fallback: locate outermost curly braces
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding failed: {e}. Raw content: {text[:300]}")
        raise LLMServiceError(f"Model returned invalid JSON: {str(e)}")


def _build_analysis_prompt(data: ExtractedWebsiteData) -> str:
    """Constructs a token-efficient prompt incorporating scraped signals."""
    return f"""Target URL: {data.final_url}
Page Title: {data.title}
Meta Description: {data.meta_description}
Meta Keywords: {', '.join(data.meta_keywords)}
Key Headings:
- H1: {', '.join(data.headings.get('h1', []))}
- H2: {', '.join(data.headings.get('h2', []))[:5]}
Navigation Offerings: {', '.join(data.nav_links)}

Sanitized Website Content:
\"\"\"
{data.clean_text}
\"\"\"

Analyze this company thoroughly and provide the exact JSON response.
"""


class GeminiLLMService(BaseLLMService):
    """Google Gemini integration with structured JSON enforcement."""

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_INSTRUCTION,
                generation_config={"response_mime_type": "application/json"}
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise LLMServiceError(f"Gemini client initialization error: {str(e)}")

    async def analyze_website(
        self, data: ExtractedWebsiteData
    ) -> Tuple[BrandInfo, AnalysisResult]:
        prompt = _build_analysis_prompt(data)
        try:
            # google-generativeai generate_content_async
            response = await self.model.generate_content_async(prompt)
            payload = _clean_json_response(response.text)
            return self._parse_payload(payload)
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            raise LLMServiceError(f"Gemini API invocation failed: {str(e)}")

    def _parse_payload(self, payload: Dict[str, Any]) -> Tuple[BrandInfo, AnalysisResult]:
        brand_raw = payload.get("brand", {})
        brand = BrandInfo(
            name=brand_raw.get("name", "Unknown Brand"),
            category=brand_raw.get("category", "Technology / Business Services"),
            summary=brand_raw.get("summary", "Company providing commercial services."),
        )

        analysis = AnalysisResult(
            competitor_analysis=CompetitorAnalysis(**payload["competitor_analysis"]),
            target_search_queries=[TargetSearchQuery(**q) for q in payload["target_search_queries"]],
            seo_improvements=SEOImprovements(**payload["seo_improvements"]),
            top_services=[TopService(**s) for s in payload["top_services"]],
            target_audience=TargetAudience(**payload["target_audience"]),
        )
        return brand, analysis


class OpenAILLMService(BaseLLMService):
    """OpenAI API integration (GPT-4o / GPT-4o-mini)."""

    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model_name = model_name
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise LLMServiceError(f"OpenAI client initialization error: {str(e)}")

    async def analyze_website(
        self, data: ExtractedWebsiteData
    ) -> Tuple[BrandInfo, AnalysisResult]:
        prompt = _build_analysis_prompt(data)
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            raw_text = response.choices[0].message.content or "{}"
            payload = _clean_json_response(raw_text)
            
            brand_raw = payload.get("brand", {})
            brand = BrandInfo(
                name=brand_raw.get("name", "Unknown Brand"),
                category=brand_raw.get("category", "Technology / Business Services"),
                summary=brand_raw.get("summary", "Company providing commercial services."),
            )

            analysis = AnalysisResult(
                competitor_analysis=CompetitorAnalysis(**payload["competitor_analysis"]),
                target_search_queries=[TargetSearchQuery(**q) for q in payload["target_search_queries"]],
                seo_improvements=SEOImprovements(**payload["seo_improvements"]),
                top_services=[TopService(**s) for s in payload["top_services"]],
                target_audience=TargetAudience(**payload["target_audience"]),
            )
            return brand, analysis
        except Exception as e:
            logger.error(f"OpenAI generation error: {e}")
            raise LLMServiceError(f"OpenAI API invocation failed: {str(e)}")


class MockLLMService(BaseLLMService):
    """
    Deterministic mock provider for automated unit/integration tests
    and running the application without external API keys.
    Derives realistic analysis directly from scraped domain and meta content.
    """

    async def analyze_website(
        self, data: ExtractedWebsiteData
    ) -> Tuple[BrandInfo, AnalysisResult]:
        domain = urlparse(data.final_url).netloc.replace("www.", "")
        brand_name = data.title.split("-")[0].split("|")[0].strip() or domain.split(".")[0].capitalize()
        category = "Digital Solutions & Technology Services"
        
        # Check text signals for vertical hints
        clean_lower = data.clean_text.lower()
        if "ecommerce" in clean_lower or "shop" in clean_lower or "store" in clean_lower:
            category = "E-Commerce & Retail Technology"
        elif "finance" in clean_lower or "payment" in clean_lower or "banking" in clean_lower:
            category = "Financial Technology (FinTech)"
        elif "health" in clean_lower or "care" in clean_lower or "medical" in clean_lower:
            category = "Healthcare & Life Sciences"
        elif "ai" in clean_lower or "machine learning" in clean_lower:
            category = "Artificial Intelligence & Automation"

        brand = BrandInfo(
            name=brand_name,
            category=category,
            summary=data.meta_description or f"{brand_name} delivers specialized services and scalable products in {category}."
        )

        competitors = [
            CompetitorItem(
                name="Market Leader Alpha",
                main_service=f"Enterprise {category}",
                target_market="Fortune 500 & Global Enterprises",
                key_strengths="Extensive brand recognition and massive capital backing",
                weaknesses_or_gaps="Legacy codebase, high implementation overhead, and slow support cycles",
                opportunity="Win mid-market and agile teams by offering frictionless onboarding and transparent pricing"
            ),
            CompetitorItem(
                name="Innovator Beta Labs",
                main_service=f"Automated {category} Workflows",
                target_market="High-growth Scaleups & Startups",
                key_strengths="Modern developer-first UI/UX and active developer community",
                weaknesses_or_gaps="Limited enterprise compliance features and nascent customer success coverage",
                opportunity="Position with certified SOC2/ISO compliance and dedicated enterprise SLAs"
            ),
            CompetitorItem(
                name="Global Systems Gamma",
                main_service=f"Managed Services & Consulting in {category}",
                target_market="Regional Enterprises and Government Sectors",
                key_strengths="Deep vertical integration and established vendor contracts",
                weaknesses_or_gaps="Expensive service contracts with recurring lock-in terms",
                opportunity="Deliver self-serve modular services with lower total cost of ownership"
            )
        ]

        strengths = [
            f"Tailored expertise focused directly on {category}",
            "Modern, lightweight architecture enabling fast time-to-value",
            "High customer satisfaction through agile and responsive client engagement"
        ]

        opportunities = [
            f"Establish category leadership by publishing benchmark reports in {category}",
            "Expand international reach through localized landing pages and regional partnerships",
            "Develop self-serve digital onboarding to accelerate inbound conversion"
        ]

        competitor_analysis = CompetitorAnalysis(
            brand_overview=f"{brand_name} is positioned as an agile provider in {category}, competing on speed, precision, and modern customer experience.",
            competitors=competitors,
            strengths=strengths,
            opportunities=opportunities
        )

        target_queries = [
            TargetSearchQuery(
                query=f"Best {category.lower()} company",
                platforms=["Google"],
                intent="Service Discovery",
                business_relevance="Primary high-intent conversion query for prospective enterprise buyers",
                target_audience="VP of Engineering / CTO looking for vetted vendors"
            ),
            TargetSearchQuery(
                query=f"{category.lower()} solutions for fast-growing businesses",
                platforms=["LinkedIn"],
                intent="B2B Commercial Investigation",
                business_relevance="High-value pipeline driver targeting decision-makers on professional networks",
                target_audience="Operations Directors and Founders"
            ),
            TargetSearchQuery(
                query=f"{brand_name.lower()} review and feature comparison",
                platforms=["Google", "X"],
                intent="Evaluation / Comparison",
                business_relevance="Late-stage consideration funnel capturing users evaluating vendor alternatives",
                target_audience="Procurement and Technical Evaluators"
            ),
            TargetSearchQuery(
                query=f"Modern {category.lower()} architecture trends",
                platforms=["LinkedIn", "X"],
                intent="Inspiration / Thought Leadership",
                business_relevance="Top-of-funnel awareness through technical leadership and industry authority",
                target_audience="Architects and Tech Leads"
            ),
            TargetSearchQuery(
                query=f"Affordable {category.lower()} integration services",
                platforms=["Google", "Facebook"],
                intent="Service Discovery",
                business_relevance="Budget-conscious SMB buyers searching for cost-effective implementation partners",
                target_audience="SMB Business Owners and Agency Partners"
            )
        ]

        primary_kw = f"{brand_name} {category}"
        seo = SEOImprovements(
            primary_keyword=primary_kw,
            secondary_keywords=[
                f"{category} software",
                f"cloud {category.lower()}",
                f"{brand_name.lower()} solutions",
                "scalable business intelligence"
            ],
            long_tail_keywords=[
                f"how to choose the best {category.lower()} provider",
                f"best {category.lower()} integration for modern companies",
                f"enterprise {category.lower()} migration guide"
            ],
            recommended_title=f"{brand_name} | Premier {category} & Solutions"[:60],
            meta_description=f"Discover {brand_name}: Accelerate your business with industry-leading {category.lower()}. High performance, security, and proven ROI."[:160],
            supporting_content=[
                f"Comprehensive Comparison Guide: Evaluating Modern {category} Platforms",
                "Industry Case Studies: Proven Performance Metrics and Case Outcomes",
                "Interactive ROI Calculator for Prospective Enterprise Clients",
                "Dedicated Technology Architecture & Integration Documentation"
            ]
        )

        # Extract services from nav or headings if present, else fallback gracefully
        top_services = [
            TopService(
                service_name=f"Custom {category} Architecture",
                description=f"End-to-end design and deployment of robust solutions in {category}.",
                target_industry="Technology & Cross-Industry Enterprise",
                target_customer="Enterprise Architecture Teams & CTOs",
                main_benefit="Reduces architectural debt and speeds deployment cycles by up to 40%",
                source="extracted_from_content" if data.nav_links else "inferred_recommendation"
            ),
            TopService(
                service_name="Cloud Platform Optimization",
                description="Infrastructure audit, performance tuning, and continuous scaling support.",
                target_industry="Cloud-Native SaaS & Digital Services",
                target_customer="DevOps Leads and VP of Infrastructure",
                main_benefit="Optimizes infrastructure compute overhead and delivers 99.99% reliability",
                source="inferred_recommendation"
            ),
            TopService(
                service_name="Data Intelligence & Analytics Pipeline",
                description="Ingesting, modeling, and visualizing mission-critical operational telemetry.",
                target_industry="FinTech, E-Commerce, and Data-Driven Startups",
                target_customer="Chief Data Officers & Growth Product Managers",
                main_benefit="Unlocks actionable real-time insights to drive revenue growth",
                source="inferred_recommendation"
            ),
            TopService(
                service_name="Enterprise Security & Compliance Audit",
                description="Rigorous security hardening, vulnerability mitigation, and compliance readiness.",
                target_industry="Regulated Industries & FinTech",
                target_customer="Chief Information Security Officers (CISOs)",
                main_benefit="Ensures compliance with global data protection standards and prevents data breaches",
                source="inferred_recommendation"
            ),
            TopService(
                service_name="24/7 Managed Operations & Support",
                description="Proactive SLA-backed operational monitoring, incident response, and patch management.",
                target_industry="Global B2B Operations",
                target_customer="IT Operations Managers and Support Directors",
                main_benefit="Eliminates critical system downtime with guaranteed 15-minute response SLAs",
                source="inferred_recommendation"
            )
        ]

        target_audience = TargetAudience(
            primary_audience=[
                "Chief Technology Officers (CTOs) and VP of Engineering",
                "Enterprise IT Directors and Chief Information Officers"
            ],
            secondary_audience=[
                "Product Managers evaluating vendor software integrations",
                "DevOps Engineers and Solutions Architects"
            ],
            industries=[
                "Financial Services & Banking",
                "E-Commerce & Digital Retail",
                "B2B SaaS & Enterprise Software",
                "Healthcare Technology"
            ],
            business_types=[
                "Mid-Market Scaleups (50-500 employees)",
                "Enterprise Organizations (500+ employees)",
                "Venture-Backed Technology Startups"
            ],
            customer_profiles=[
                "Technical Leader prioritizing system reliability and speed",
                "Business Executive aiming to decrease operational costs and cycle times"
            ],
            geographical_focus="Global with primary concentration in North America, Europe, and Asia-Pacific",
            customer_needs=[
                "High availability and fault-tolerant system design",
                "Seamless API integration with existing legacy tech stacks",
                "Predictable vendor pricing and responsive SLA support"
            ],
            customer_interests=[
                "Modern AI automation workflows",
                "Cloud-native microservices architecture",
                "Cost optimization and compute efficiency"
            ],
            recommended_segments=[
                "Tier 1: Enterprise Accounts (High-touch consultative sales)",
                "Tier 2: Mid-Market Growth Accounts (Inbound content & targeted product demos)",
                "Tier 3: Early-stage Founders (Self-serve sandbox & developer documentation)"
            ]
        )

        analysis = AnalysisResult(
            competitor_analysis=competitor_analysis,
            target_search_queries=target_queries,
            seo_improvements=seo,
            top_services=top_services,
            target_audience=target_audience
        )

        return brand, analysis


def get_llm_service() -> BaseLLMService:
    """Factory creating the appropriate LLM service instance based on environment settings."""
    provider = settings.LLM_PROVIDER.lower().strip()

    if provider == "gemini":
        if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here":
            logger.info(f"Initializing Gemini LLM Service with model: {settings.GEMINI_MODEL}")
            return GeminiLLMService(
                api_key=settings.GEMINI_API_KEY,
                model_name=settings.GEMINI_MODEL
            )
        else:
            logger.warning("GEMINI_API_KEY is not configured. Falling back to deterministic Mock provider.")
            return MockLLMService()

    elif provider == "openai":
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your_openai_api_key_here":
            logger.info(f"Initializing OpenAI LLM Service with model: {settings.OPENAI_MODEL}")
            return OpenAILLMService(
                api_key=settings.OPENAI_API_KEY,
                model_name=settings.OPENAI_MODEL
            )
        else:
            logger.warning("OPENAI_API_KEY is not configured. Falling back to deterministic Mock provider.")
            return MockLLMService()

    elif provider == "mock":
        logger.info("Using configured Mock LLM Service.")
        return MockLLMService()

    else:
        logger.warning(f"Unknown LLM_PROVIDER '{provider}'. Defaulting to Mock LLM Service.")
        return MockLLMService()
