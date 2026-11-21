import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple


class SSRFValidationError(ValueError):
    """Raised when a URL targets a restricted, loopback, or private network range."""
    pass


class InvalidURLError(ValueError):
    """Raised when a URL is syntactically invalid or uses an unsupported scheme."""
    pass


def validate_url_security(url: str, block_private: bool = True) -> Tuple[str, str]:
    """
    Validates URL syntax and performs strict Server-Side Request Forgery (SSRF) checks.
    
    1. Ensures scheme is strictly http or https.
    2. Resolves DNS to all IP targets.
    3. Blocks loopback (127.0.0.1, ::1), private RFC1918 ranges, link-local (169.254.169.254 metadata),
       multicast, and reserved addresses.
       
    Returns:
        Tuple of (clean_url, resolved_ip)
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL string is required.")
        
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        # If user provided domain without scheme, prepend https://
        if "://" not in url:
            url = f"https://{url}"
        else:
            raise InvalidURLError("Invalid URL scheme. Only http:// and https:// protocols are supported.")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidURLError(f"Failed to parse URL: {str(e)}")

    if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
        raise InvalidURLError("Unsupported scheme. Only http and https are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError("URL must contain a valid hostname.")

    # Reject obvious localhost / zero address strings
    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise SSRFValidationError("Access to localhost / loopback addresses is forbidden.")

    if not block_private:
        return url, hostname

    # DNS Resolution and IP checking
    try:
        # Resolve both IPv4 and IPv6 addresses
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise InvalidURLError(f"Could not resolve domain '{hostname}': {str(e)}")
    except Exception as e:
        raise InvalidURLError(f"DNS resolution error for '{hostname}': {str(e)}")

    if not addr_info:
        raise InvalidURLError(f"No IP addresses resolved for domain '{hostname}'.")

    resolved_ip_str = None
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        resolved_ip_str = ip_str

        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFValidationError(f"Invalid resolved IP address: {ip_str}")

        # Strict checks against private / internal targets
        if ip_obj.is_loopback:
            raise SSRFValidationError(f"Target resolves to loopback IP {ip_str}, which is blocked.")
        if ip_obj.is_private:
            raise SSRFValidationError(f"Target resolves to private network IP {ip_str}, which is blocked.")
        if ip_obj.is_link_local:
            raise SSRFValidationError(f"Target resolves to link-local/cloud metadata IP {ip_str}, which is blocked.")
        if ip_obj.is_multicast:
            raise SSRFValidationError(f"Target resolves to multicast IP {ip_str}, which is blocked.")
        if ip_obj.is_reserved:
            raise SSRFValidationError(f"Target resolves to reserved IP {ip_str}, which is blocked.")
        if ip_obj.is_unspecified:
            raise SSRFValidationError(f"Target resolves to unspecified IP {ip_str}, which is blocked.")

        # Additional protection against AWS / GCP / Azure metadata endpoint (169.254.169.254)
        if str(ip_obj) == "169.254.169.254":
            raise SSRFValidationError("Target resolves to cloud instance metadata endpoint, which is blocked.")

    return url, resolved_ip_str or hostname
