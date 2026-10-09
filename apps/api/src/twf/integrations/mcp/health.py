"""Central, deterministic health policy; health never grants operation authority."""

from twf.integrations.mcp.contracts import Code

# Tool errors do not count as transport failures. A normal success resets the streak.
OUTAGE_THRESHOLD = 3
PROVIDER_FAILURES = {Code.UNAVAILABLE.value, Code.TIMEOUT.value, Code.CONTRACT_MISMATCH.value}
AUTH_FAILURES = {Code.AUTH_REQUIRED.value, Code.AUTH_FAILED.value, Code.REAUTH_REQUIRED.value}


def family(tool: str | None) -> str:
    if tool == "get_stock_quote":
        return "REFERENCE"
    if tool in {"get_market_news", "get_stock_events"}:
        return "NEWS"
    if tool in {"get_fii_dii_detail", "get_fpi_sectors"}:
        return "FLOWS"
    if tool in {"get_india_vix", "get_market_pulse"}:
        return "VIX_MARKET_PULSE"
    if tool == "get_index_performance":
        return "INDEX_PERFORMANCE"
    return "GENERAL_MCP"
