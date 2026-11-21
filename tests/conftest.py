import pytest
from starlette.testclient import TestClient
from app.main import app
from app.services.website_extractor import ExtractedWebsiteData


@pytest.fixture
def mock_html_content() -> str:
    """Sample realistic corporate HTML for deterministic parser testing."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Acme Cloud Solutions | Next-Gen Enterprise Infrastructure</title>
    <meta name="description" content="Acme Cloud delivers resilient, high-speed cloud infrastructure and Kubernetes automation for high-growth enterprises.">
    <meta name="keywords" content="cloud infrastructure, kubernetes, devops automation, scalable hosting">
    <meta property="og:title" content="Acme Cloud Solutions">
    <meta property="og:description" content="Resilient cloud infrastructure and automated DevOps.">
    <meta property="og:site_name" content="Acme Cloud">
</head>
<body>
    <header>
        <nav>
            <a href="/products">Products</a>
            <a href="/services/managed-k8s">Managed Kubernetes</a>
            <a href="/services/cloud-migration">Cloud Migration</a>
            <a href="/services/observability">Observability Pipeline</a>
            <a href="/pricing">Pricing</a>
        </nav>
    </header>
    <main>
        <h1>Modern Cloud Infrastructure Designed for Scale</h1>
        <p>Acme Cloud transforms how software engineering teams deploy, monitor, and scale distributed applications in the cloud.</p>
        
        <h2>High Performance Container Orchestration</h2>
        <p>Our managed Kubernetes platform guarantees 99.999% uptime with zero-downtime rolling deployments, automated failover, and multi-region failover clusters.</p>
        
        <h2>Full-Stack Observability and Telemetry</h2>
        <p>Collect logs, metrics, and distributed traces with ultra-low overhead. Detect anomalies before they impact your end-users.</p>
        
        <h2>Automated Security and Compliance</h2>
        <p>SOC 2 Type II, HIPAA, and GDPR compliant infrastructure out-of-the-box. End-to-end encryption at rest and in transit.</p>
    </main>
    <footer>
        <p>&copy; 2026 Acme Cloud Inc. All rights reserved.</p>
    </footer>
</body>
</html>
"""


@pytest.fixture
def mock_extracted_data(mock_html_content: str) -> ExtractedWebsiteData:
    """Mock parsed ExtractedWebsiteData object."""
    return ExtractedWebsiteData(
        requested_url="https://acmecloud.example.com",
        final_url="https://acmecloud.example.com",
        status_code=200,
        title="Acme Cloud Solutions | Next-Gen Enterprise Infrastructure",
        meta_description="Acme Cloud delivers resilient, high-speed cloud infrastructure and Kubernetes automation.",
        meta_keywords=["cloud infrastructure", "kubernetes", "devops automation"],
        og_data={"title": "Acme Cloud Solutions", "site_name": "Acme Cloud"},
        headings={
            "h1": ["Modern Cloud Infrastructure Designed for Scale"],
            "h2": [
                "High Performance Container Orchestration",
                "Full-Stack Observability and Telemetry",
                "Automated Security and Compliance"
            ],
            "h3": []
        },
        nav_links=["Managed Kubernetes", "Cloud Migration", "Observability Pipeline"],
        clean_text=(
            "Modern Cloud Infrastructure Designed for Scale\n"
            "Acme Cloud transforms how engineering teams deploy, monitor, and scale applications.\n"
            "Managed Kubernetes platform guarantees 99.999% uptime with zero-downtime rolling deployments.\n"
            "Full-Stack Observability and Telemetry detects anomalies.\n"
            "Automated Security and Compliance with SOC 2 Type II and HIPAA compliance."
        ),
        raw_text_length=1200
    )


@pytest.fixture
def client():
    """Synchronous test client for testing FastAPI endpoints."""
    with TestClient(app) as test_client:
        yield test_client
