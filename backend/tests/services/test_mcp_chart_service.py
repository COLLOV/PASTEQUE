import asyncio
import ssl

from insight_backend.services import mcp_chart_service as service


def _ssl_mode(client):
    ctx = client._transport._pool._ssl_context
    return ctx.verify_mode, ctx.check_hostname


def test_openai_http_client_respects_llm_verify_ssl():
    client_true = service._openai_http_client(True)
    client_false = service._openai_http_client(False)

    try:
        verify_true, hostname_true = _ssl_mode(client_true)
        verify_false, hostname_false = _ssl_mode(client_false)

        assert verify_true == ssl.CERT_REQUIRED
        assert hostname_true is True
        assert verify_false == ssl.CERT_NONE
        assert hostname_false is False
    finally:
        asyncio.run(client_true.aclose())
        asyncio.run(client_false.aclose())
        service._openai_http_client.cache_clear()
