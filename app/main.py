import logging
import sys
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas import (
    ErrorResponse,
    LinkAnalysisRequest,
    LinkAnalysisResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMServiceError
from app.services.website_extractor import (
    WebsiteContentEmptyError,
    WebsiteExtractorError,
    WebsiteUnreachableError,
)
from app.utils.validators import InvalidURLError, SSRFValidationError

# Configure structured logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("link_analysis_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for service initialization and graceful shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Configured LLM Provider: {settings.LLM_PROVIDER}")
    logger.info(f"Listening on http://{settings.HOST}:{settings.PORT}")
    yield
    logger.info("Shutting down link analysis service cleanly.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-grade AI-powered website link analysis and competitive intelligence service. "
        "Extracts website content, understands business signals via LLM, and delivers structured "
        "intelligence across 5 core pillars: Competitor Analysis, Target Search Queries, "
        "SEO Improvements, Top 5 Services, and Target Audience Identification."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Measures total HTTP request processing duration."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    return response


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(SSRFValidationError)
async def ssrf_exception_handler(request: Request, exc: SSRFValidationError):
    """Blocks SSRF attempts and returns HTTP 400 Bad Request."""
    logger.warning(f"SSRF violation blocked from {request.client.host}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            success=False,
            detail=f"Security violation: {str(exc)}",
            error_code="SSRF_SECURITY_VIOLATION",
        ).model_dump(),
    )


@app.exception_handler(InvalidURLError)
async def invalid_url_exception_handler(request: Request, exc: InvalidURLError):
    """Handles malformed URLs and invalid schemes."""
    logger.warning(f"Invalid URL rejected: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            success=False,
            detail=str(exc),
            error_code="INVALID_URL_FORMAT",
        ).model_dump(),
    )


@app.exception_handler(WebsiteUnreachableError)
async def unreachable_exception_handler(request: Request, exc: WebsiteUnreachableError):
    """Handles unreachable external websites with HTTP 502 Bad Gateway."""
    logger.error(f"Website unreachable error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            success=False,
            detail=f"Failed to fetch target website: {str(exc)}",
            error_code="TARGET_WEBSITE_UNREACHABLE",
        ).model_dump(),
    )


@app.exception_handler(WebsiteContentEmptyError)
async def empty_content_exception_handler(request: Request, exc: WebsiteContentEmptyError):
    """Handles empty or unparseable website HTML with HTTP 422 Unprocessable Entity."""
    logger.error(f"Empty website content error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            success=False,
            detail=str(exc),
            error_code="EMPTY_WEBSITE_CONTENT",
        ).model_dump(),
    )


@app.exception_handler(LLMServiceError)
async def llm_exception_handler(request: Request, exc: LLMServiceError):
    """Handles LLM provider communication and generation failures."""
    logger.error(f"LLM service failure: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            success=False,
            detail=f"AI model processing failure: {str(exc)}",
            error_code="LLM_GENERATION_FAILED",
        ).model_dump(),
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get(
    "/health",
    tags=["System"],
    summary="Service Health Check",
    response_description="Returns operational health status and active configuration.",
)
async def health_check():
    """Health check endpoint for container probes and monitoring."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
        "ssrf_protection": settings.BLOCK_PRIVATE_NETWORKS,
    }


@app.get(
    "/",
    tags=["System"],
    summary="Root Endpoint",
)
async def root():
    """Root metadata endpoint with documentation navigation."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "analysis_endpoint": "POST /link-analysis",
    }


@app.post(
    "/link-analysis",
    response_model=LinkAnalysisResponse,
    status_code=status.HTTP_200_OK,
    tags=["Link Analysis"],
    summary="Analyze Website Link",
    response_description="Returns 5-pillar structured competitive and SEO intelligence.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid URL or SSRF attempt"},
        422: {"model": ErrorResponse, "description": "Website returned empty content"},
        502: {"model": ErrorResponse, "description": "Target website unreachable or timed out"},
        500: {"model": ErrorResponse, "description": "Internal server or LLM processing failure"},
    },
)
async def analyze_link(payload: LinkAnalysisRequest):
    """
    Submits a public website URL for comprehensive intelligence extraction:
    - **Competitor vs Brand Analysis**: Direct comparison against at least 3 competitors.
    - **Top 5 Target Search Queries**: Multi-platform discovery queries (Google, LinkedIn, etc.).
    - **SEO Improvement**: Keywords, title tag, meta description, and content clusters.
    - **Top 5 Services**: Core offerings with target industry and quantifiable benefits.
    - **Target Audience Identification**: Decision-makers, segments, and customer pain points.
    """
    analysis_service = AnalysisService()
    result = await analysis_service.execute_link_analysis(payload.url)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
