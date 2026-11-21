import logging
import time
from typing import Optional

from app.config import settings
from app.schemas import (
    AnalysisMetadata,
    AnalysisResult,
    BrandInfo,
    LinkAnalysisResponse,
)
from app.services.competitor_service import CompetitorService
from app.services.llm_service import BaseLLMService, get_llm_service
from app.services.website_extractor import WebsiteExtractor, ExtractedWebsiteData

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Main orchestration service coordinating website extraction,
    LLM intelligence processing, competitor validation, and response synthesis.
    """

    def __init__(
        self,
        extractor: Optional[WebsiteExtractor] = None,
        llm_service: Optional[BaseLLMService] = None,
    ):
        self.extractor = extractor or WebsiteExtractor()
        self.llm_service = llm_service or get_llm_service()

    async def execute_link_analysis(self, url: str) -> LinkAnalysisResponse:
        """
        Executes end-to-end 5-pillar link analysis on target website:
        1. Website fetch & content extraction
        2. LLM processing & structured extraction
        3. Competitor enrichment & validation
        4. Performance telemetry assembly
        """
        start_time = time.perf_counter()
        logger.info(f"Initiating link analysis for: {url}")

        # Step 1: Safe extraction
        extracted_data: ExtractedWebsiteData = await self.extractor.fetch_and_extract(url)
        extract_duration = time.perf_counter() - start_time
        logger.info(
            f"Extraction completed in {extract_duration:.2f}s for {extracted_data.final_url}. "
            f"Parsed {len(extracted_data.clean_text)} characters."
        )

        # Step 2: LLM analysis
        brand, analysis = await self.llm_service.analyze_website(extracted_data)

        # Step 3: Competitor enrichment & sanity checks
        analysis.competitor_analysis = CompetitorService.validate_and_enrich_competitors(
            analysis.competitor_analysis
        )

        # Step 4: Assemble telemetry
        total_duration = time.perf_counter() - start_time
        provider_name = settings.LLM_PROVIDER
        model_name = (
            settings.GEMINI_MODEL
            if provider_name == "gemini"
            else (settings.OPENAI_MODEL if provider_name == "openai" else "deterministic-mock")
        )

        metadata = AnalysisMetadata(
            duration_seconds=round(total_duration, 3),
            model_provider=provider_name,
            model_name=model_name,
            extracted_text_length=len(extracted_data.clean_text),
        )

        return LinkAnalysisResponse(
            success=True,
            website=extracted_data.final_url,
            brand=brand,
            analysis=analysis,
            metadata=metadata,
        )
