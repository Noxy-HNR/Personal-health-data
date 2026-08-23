"""Unified local health MCP entrypoint.
Loads the existing Oura tools and adds public medical-reference tools.
"""
from medical_tools import register_medical_tools
from oura_service import HOST, PORT, mcp

register_medical_tools(mcp)


def main() -> None:
    import uvicorn
    app = mcp.streamable_http_app()
    print(f"Personal Health MCP: http://{HOST}:{PORT}/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"Oura OAuth: http://{HOST}:{PORT}/oauth/start")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
