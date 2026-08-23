from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any


def register_pubmed_tools(mcp, medical_tools):
    @mcp.tool(name="search_pubmed")
    def search_pubmed(
        query: str,
        max_results: int = 5,
        years: int | None = 5,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        """Search PubMed and return compact, evidence-backed citations.

        Results include an extractive one-sentence abstract summary when an abstract
        is available, so the model does not have to fetch large raw PubMed payloads
        or invent summaries from citation metadata alone.
        """
        if not query.strip():
            raise ValueError("query is required")
        limit = max(1, min(int(max_results), 10))
        term = query.strip()
        if years is not None:
            y = max(1, min(int(years), 100))
            cutoff = date.today().year - y
            term = f"({term}) AND ({cutoff}:3000[dp])"
        allowed_sort = {"relevance", "date", "pub date", "first author", "journal"}
        sort = sort if sort in allowed_sort else "relevance"

        search = medical_tools.get(
            f"{medical_tools.NCBI}/esearch.fcgi",
            medical_tools.ncbi({
                "db": "pubmed", "term": term, "retmode": "json",
                "retmax": limit, "sort": sort,
            }),
        ).json()["esearchresult"]
        ids = search.get("idlist", [])
        if not ids:
            return {
                "query": query,
                "count": int(search.get("count", 0)),
                "results": [],
                "source": "PubMed/NCBI",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/",
            }

        summary_xml = medical_tools.get(
            f"{medical_tools.NCBI}/esummary.fcgi",
            medical_tools.ncbi({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}),
        ).text
        citations = {x["pmid"]: x for x in medical_tools.summaries(summary_xml)}

        # One batched request for abstracts; never expose the full XML to the model.
        abstract_xml = medical_tools.get(
            f"{medical_tools.NCBI}/efetch.fcgi",
            medical_tools.ncbi({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}),
        ).text
        abstracts = _abstracts_by_pmid(abstract_xml)

        results = []
        for pmid in ids:
            citation = citations.get(pmid, {"pmid": pmid})
            abstract = abstracts.get(pmid, "")
            results.append({
                "pmid": pmid,
                "title": citation.get("Title", ""),
                "authors": citation.get("AuthorList", []),
                "publication_year": _year(citation.get("PubDate") or citation.get("EPubDate") or ""),
                "journal": citation.get("FullJournalName") or citation.get("Source", ""),
                "doi": citation.get("DOI") or None,
                "summary": _one_sentence_summary(abstract),
                "abstract_available": bool(abstract),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })

        return {
            "query": query,
            "count": int(search.get("count", 0)),
            "years_filter": years,
            "sort": sort,
            "results": results,
            "source": "PubMed/NCBI",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/",
        }


def _year(value: str) -> int | None:
    m = re.search(r"\b(19|20)\d{2}\b", value or "")
    return int(m.group(0)) if m else None


def _abstracts_by_pmid(xml: str) -> dict[str, str]:
    root = ET.fromstring(xml)
    out: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID") or ""
        parts = []
        for node in article.findall(".//Abstract/AbstractText"):
            text = " ".join("".join(node.itertext()).split())
            if text:
                label = node.attrib.get("Label")
                parts.append(f"{label}: {text}" if label else text)
        if pmid:
            out[pmid] = " ".join(parts)
    return out


def _one_sentence_summary(abstract: str) -> str | None:
    if not abstract:
        return None
    text = " ".join(abstract.split())
    match = re.search(r".+?[.!?](?:\s|$)", text)
    if match:
        sentence = match.group(0).strip()
    else:
        sentence = text[:320].rstrip(" ,;:") + ("…" if len(text) > 320 else "")
    if len(sentence) > 360:
        sentence = sentence[:357].rsplit(" ", 1)[0] + "…"
    return sentence
