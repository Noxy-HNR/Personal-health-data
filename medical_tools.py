from __future__ import annotations
import os, xml.etree.ElementTree as ET
from datetime import date
from typing import Any
import httpx

NCBI="https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MEDLINE="https://wsearch.nlm.nih.gov/ws/query"
MEDCONNECT="https://connect.medlineplus.gov/service"
CT="https://clinicaltables.nlm.nih.gov/api"
NPI="https://npiregistry.cms.hhs.gov/api/"
CMS="https://api.coverage.cms.gov/v1"
EMAIL=os.getenv("NCBI_EMAIL","").strip(); APIKEY=os.getenv("NCBI_API_KEY","").strip(); TOOL=os.getenv("NCBI_TOOL","personal-health-mcp").strip()

def get(url, params=None, timeout=30):
    r=httpx.get(url,params=params or {},headers={"User-Agent":"Personal-Health-MCP/1.0"},timeout=timeout); r.raise_for_status(); return r

def ncbi(p):
    p=dict(p); p["tool"]=TOOL
    if EMAIL:p["email"]=EMAIL
    if APIKEY:p["api_key"]=APIKEY
    return p

def summaries(xml):
    root=ET.fromstring(xml); out=[]
    for d in root.findall(".//DocSum"):
        x={"pmid":d.findtext("Id") or ""}
        for c in d.findall("Item"):
            n=c.attrib.get("Name","")
            if n in {"Title","PubDate","EPubDate","Source","FullJournalName","DOI"}: x[n]="".join(c.itertext()).strip()
            elif n=="AuthorList": x[n]=["".join(a.itertext()).strip() for a in c.findall("Item")]
        if x["pmid"]:x["url"]=f"https://pubmed.ncbi.nlm.nih.gov/{x['pmid']}/"
        out.append(x)
    return out

def ctsearch(path,q,limit,sf,df,ef=None):
    p={"terms":q.strip(),"sf":sf,"df":df,"cf":"code","maxList":max(1,min(int(limit),100))}
    if ef:p["ef"]=ef
    return get(f"{CT}/{path}/v3/search",p).json()

def register_medical_tools(mcp):
    @mcp.tool()
    def medical_sources()->dict[str,Any]:
        """List medical reference sources available to the model."""
        return {"sources":[
          {"name":"PubMed/NCBI","tools":["search_pubmed","get_pubmed_article"],"auth":"optional NCBI email/API key"},
          {"name":"MedlinePlus","tools":["search_medlineplus","lookup_medlineplus_code"],"auth":"none"},
          {"name":"NLM Clinical Tables","tools":["lookup_icd10","lookup_icd11","search_medical_conditions","search_drugs","search_loinc"],"auth":"none"},
          {"name":"NPPES NPI Registry","tools":["search_npi_registry"],"auth":"none"},
          {"name":"CMS Medicare Coverage Database","tools":["cms_coverage_whats_new","cms_national_coverage_annual"],"auth":"none for these public endpoints"}],
          "note":"Reference information only; preserve source attribution and dates."}

    @mcp.tool()
    def search_pubmed(query:str,max_results:int=10,years:int|None=None,sort:str="relevance")->dict[str,Any]:
        """Search PubMed biomedical literature."""
        if not query.strip():raise ValueError("query is required")
        term=query.strip()
        if years:
            cutoff=date.today().year-max(1,min(int(years),100)); term=f"({term}) AND ({cutoff}:3000[dp])"
        sort=sort if sort in {"relevance","date","pub date","first author","journal"} else "relevance"
        s=get(f"{NCBI}/esearch.fcgi",ncbi({"db":"pubmed","term":term,"retmode":"json","retmax":max(1,min(int(max_results),50)),"sort":sort})).json()["esearchresult"]
        ids=s.get("idlist",[])
        if not ids:return {"query":query,"count":int(s.get("count",0)),"results":[],"source":"PubMed/NCBI"}
        x=get(f"{NCBI}/esummary.fcgi",ncbi({"db":"pubmed","id":",".join(ids),"retmode":"xml"})).text
        return {"query":query,"count":int(s.get("count",0)),"results":summaries(x),"source":"PubMed/NCBI","source_url":"https://pubmed.ncbi.nlm.nih.gov/"}

    @mcp.tool()
    def get_pubmed_article(pmid:str,include_abstract:bool=True)->dict[str,Any]:
        """Get PubMed citation metadata and optional abstract for a PMID."""
        if not str(pmid).isdigit():raise ValueError("pmid must be numeric")
        pmid=str(pmid); x=get(f"{NCBI}/esummary.fcgi",ncbi({"db":"pubmed","id":pmid,"retmode":"xml"})).text
        out={"pmid":pmid,"citation":(summaries(x) or [None])[0],"source":"PubMed/NCBI","url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
        if include_abstract:
            root=ET.fromstring(get(f"{NCBI}/efetch.fcgi",ncbi({"db":"pubmed","id":pmid,"retmode":"xml"})).text); parts=[]
            for n in root.findall(".//AbstractText"):
                t="".join(n.itertext()).strip()
                if t:parts.append(f"{n.attrib.get('Label')}: {t}" if n.attrib.get("Label") else t)
            out["abstract"]="\n\n".join(parts) if parts else None
        return out

    @mcp.tool()
    def search_medlineplus(query:str,max_results:int=10,language:str="en")->dict[str,Any]:
        """Search MedlinePlus health topics."""
        if not query.strip():raise ValueError("query is required")
        db="healthTopicsSpanish" if language.lower().startswith("es") else "healthTopics"
        root=ET.fromstring(get(MEDLINE,{"db":db,"term":query.strip(),"retmax":max(1,min(int(max_results),50)),"rettype":"all","tool":TOOL,"email":EMAIL}).text); out=[]
        for d in root.findall(".//document"):
            x={}
            for c in d.findall("content"):
                n=c.attrib.get("name","");t="".join(c.itertext()).strip()
                if n and t:x[n]=t
            if x:out.append(x)
        return {"query":query,"results":out,"source":"MedlinePlus.gov","source_url":"https://medlineplus.gov/"}

    @mcp.tool()
    def lookup_icd10(code_or_term:str,max_results:int=10)->dict[str,Any]:
        """Look up current ICD-10-CM code descriptions."""
        p=ctsearch("icd10cm",code_or_term,max_results,"code,name","code,name"); rows=p[3] if len(p)>3 else []
        return {"query":code_or_term,"total":p[0] if p else 0,"results":[{"code":r[0],"name":r[1]} for r in rows if len(r)>1],"source":"NLM Clinical Tables / CDC ICD-10-CM"}

    @mcp.tool()
    def lookup_icd11(code_or_term:str,max_results:int=10)->dict[str,Any]:
        """Look up ICD-11 codes and titles."""
        p=ctsearch("icd11_codes",code_or_term,max_results,"code,title","code,title"); rows=p[3] if len(p)>3 else []
        return {"query":code_or_term,"total":p[0] if p else 0,"results":[{"code":r[0],"title":r[1]} for r in rows if len(r)>1],"source":"NLM Clinical Tables / WHO ICD-11"}

    @mcp.tool()
    def search_medical_conditions(query:str,max_results:int=10)->dict[str,Any]:
        """Search medical conditions, synonyms and ICD-10-CM mappings."""
        p=ctsearch("conditions",query,max_results,"primary_name,consumer_name","primary_name,consumer_name","icd10cm,synonyms,info_link_data"); ids=p[1] if len(p)>1 else []; extra=p[2] or {}; display=p[3] if len(p)>3 else []; out=[]
        for i,v in enumerate(ids):
            x={"id":v,"display":display[i] if i<len(display) else []}
            for k,vals in extra.items():
                if i<len(vals):x[k]=vals[i]
            out.append(x)
        return {"query":query,"total":p[0] if p else 0,"results":out,"source":"NLM Clinical Tables"}

    @mcp.tool()
    def search_drugs(query:str,max_results:int=10)->dict[str,Any]:
        """Search NLM RxTerms for drug names, strengths and dose forms."""
        p=ctsearch("rxterms",query,max_results,"DISPLAY_NAME,STRENGTH,DOSE_FORM","DISPLAY_NAME,STRENGTH,DOSE_FORM"); rows=p[3] if len(p)>3 else []
        return {"query":query,"total":p[0] if p else 0,"results":[{"display_name":r[0],"strength":r[1] if len(r)>1 else "","dose_form":r[2] if len(r)>2 else ""} for r in rows],"source":"NLM RxTerms"}

    @mcp.tool()
    def search_loinc(query:str,max_results:int=10)->dict[str,Any]:
        """Search LOINC laboratory/clinical observation codes."""
        p=ctsearch("loinc",query,max_results,"LOINC_NUM,SHORTNAME,LONG_COMMON_NAME","LOINC_NUM,SHORTNAME,LONG_COMMON_NAME"); rows=p[3] if len(p)>3 else []
        return {"query":query,"total":p[0] if p else 0,"results":[{"loinc":r[0],"short_name":r[1] if len(r)>1 else "","long_name":r[2] if len(r)>2 else ""} for r in rows],"source":"LOINC / NLM Clinical Tables"}

    @mcp.tool()
    def lookup_medlineplus_code(code:str,code_system:str="icd10cm")->dict[str,Any]:
        """Map ICD-10-CM, ICD-9-CM, SNOMED, RxNorm or NDC codes to MedlinePlus context."""
        systems={"icd10cm":"2.16.840.1.113883.6.90","icd9cm":"2.16.840.1.113883.6.103","snomed":"2.16.840.1.113883.6.96","rxnorm":"2.16.840.1.113883.6.88","ndc":"2.16.840.1.113883.6.69"}; system=systems.get(code_system.lower())
        if not system:raise ValueError(f"Unsupported code_system: {code_system}")
        return {"code":code,"code_system":code_system,"result":get(MEDCONNECT,{"mainSearchCriteria.v.cs":system,"mainSearchCriteria.v.c":code.strip(),"knowledgeResponseType":"application/json","informationRecipient.languageCode.c":"en"}).json(),"source":"MedlinePlus.gov"}

    @mcp.tool()
    def search_npi_registry(first_name:str|None=None,last_name:str|None=None,organization_name:str|None=None,city:str|None=None,state:str|None=None,taxonomy:str|None=None,npi:str|None=None,limit:int=10)->dict[str,Any]:
        """Search the US NPPES/NPI Registry for healthcare providers."""
        p={"version":"2.1","limit":max(1,min(int(limit),50))}
        for k,v in {"first_name":first_name,"last_name":last_name,"organization_name":organization_name,"city":city,"state":state,"taxonomy_description":taxonomy,"number":npi}.items():
            if v:p[k]=v
        if len(p)==2:raise ValueError("Provide at least one provider search field")
        d=get(NPI,p).json(); return {"result_count":d.get("result_count",0),"results":d.get("results",[]),"source":"NPPES NPI Registry"}

    @mcp.tool()
    def cms_coverage_whats_new(kind:str="national")->dict[str,Any]:
        """Retrieve recent CMS Medicare Coverage Database national/local updates."""
        if kind not in {"national","local"}:raise ValueError("kind must be national or local")
        r=get(f"{CMS}/reports/whats-new/{kind}/")
        try:d=r.json()
        except Exception:d=r.text
        return {"kind":kind,"data":d,"source":"CMS Medicare Coverage Database"}

    @mcp.tool()
    def cms_national_coverage_annual(year:int|None=None)->dict[str,Any]:
        """Retrieve CMS national Medicare coverage annual-report data."""
        r=get(f"{CMS}/reports/national-coverage-annual/",{"year":int(year)} if year else {})
        try:d=r.json()
        except Exception:d=r.text
        return {"year":year,"data":d,"source":"CMS Medicare Coverage Database"}
