"""Unified local health MCP entrypoint.
Loads the Oura tools and adds public medical-reference tools.
"""
import medical_tools
from oura_service import HOST, PORT, mcp

# Clinical Tables datasets have different native code fields. Let each dataset
# use its documented default instead of forcing a generic 'code' field.
def _clinical_search(path, query, max_results, sf, df, ef=None):
    params = {"terms": query.strip(), "sf": sf, "df": df, "maxList": max(1, min(int(max_results), 100))}
    if ef:
        params["ef"] = ef
    return medical_tools.get(f"{medical_tools.CT}/{path}/v3/search", params).json()

medical_tools.ctsearch = _clinical_search
medical_tools.register_medical_tools(mcp)


def main() -> None:
    import uvicorn
    app = mcp.streamable_http_app()
    print(f"Personal Health MCP: http://{HOST}:{PORT}/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"Oura OAuth: http://{HOST}:{PORT}/oauth/start")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
