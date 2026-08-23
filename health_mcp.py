"""Unified local health MCP entrypoint."""
import medical_tools
from fda_tools import register_fda_tools
from oura_service import HOST, PORT, mcp
from analytics_tools import register_analytics_tools

def _clinical_search(path, query, max_results, sf, df, ef=None):
    params={"terms":query.strip(),"sf":sf,"df":df,"maxList":max(1,min(int(max_results),100))}
    if ef: params["ef"]=ef
    return medical_tools.get(f"{medical_tools.CT}/{path}/v3/search",params).json()

medical_tools.ctsearch=_clinical_search
medical_tools.register_medical_tools(mcp)
register_fda_tools(mcp)
register_analytics_tools(mcp)


def main()->None:
    import uvicorn
    app=mcp.streamable_http_app()
    print(f"Personal Health MCP: http://{HOST}:{PORT}/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"Oura OAuth: http://{HOST}:{PORT}/oauth/start")
    uvicorn.run(app,host=HOST,port=PORT,log_level="info")


if __name__=="__main__": main()
