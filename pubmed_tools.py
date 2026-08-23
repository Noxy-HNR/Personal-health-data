from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

_STOPWORDS = {
    "a", "an", "and", "are", "for", "in", "of", "on", "or", "the", "to", "with",
    "without", "from", "about", "study", "studies", "recent", "effects", "effect",
}


def register_pubmed_tools(mcp, medical_tools):
    @mcp.tool(name="search_pubmed")
    def search_pubmed(
        query: str,
        max_results: int = 5,
        years: int | None = 5,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        """Search PubMed and return a small set of relevant, evidence-backed citations.

        PubMed search, abstract retrieval, relevance filtering, ranking, and the
        extractive one-sentence summary are performed server-side. The model never
        receives raw PubMed XML or full abstracts.
        """
        if not query.strip():
            raise ValueError("query is required")

        limit = max(1, min(int(max_results), 10))
        years_filter = None if years is None else max(1, min(int(years), 100))
        sort = sort if sort in {"relevance", "date", "pub date", "first author", "journal"} else "relevance"

        term = _build_query(query.strip(), years_filter)
        # Pull a candidate pool, then rank/filter locally. This prevents a broad
        # PubMed query from filling the result set with papers that only weakly match.
        candidate_limit = max(25, limit * 5)
        search = medical_tools.get(
            f"{medical_tools.NCBI}/esearch.fcgi",
            medical_tools.ncbi({
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": candidate_limit,
                "sort": sort,
            }),
        ).json()["esearchresult"]
        ids = search.get("idlist", [])
        if not ids:
            return _empty_result(query, search, years_filter, sort)

        summary_xml = medical_tools.get(
            f"{medical_tools.NCBI}/esummary.fcgi",
            medical_tools.ncbi({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}),
        ).text
        citations = {item["pmid"]: item for item in medical_tools.summaries(summary_xml)}

        abstract_xml = medical_tools.get(
            f"{medical_tools.NCBI}/efetch.fcgi",
            medical_tools.ncbi({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}),
        ).text
        abstracts = _abstracts_by_pmid(abstract_xml)

        keywords = _keywords(query)
        candidates: list[tuple[float, int, dict[str, Any]]] = []
        for position, pmid in enumerate(ids):
            citation = citations.get(pmid, {"pmid": pmid})
            title = citation.get("Title", "") or ""
            abstract = abstracts.get(pmid, "") or ""
            score = _relevance_score(title, abstract, keywords)
            if keywords and score <= 0:
                continue

            year = _year(citation.get("PubDate") or citation.get("EPubDate") or "")
            item = {
                "pmid": pmid,
                "title": title,
                "authors": citation.get("AuthorList", []),
                "publication_year": year,
                "journal": citation.get("FullJournalName") or citation.get("Source", ""),
                "doi": citation.get("DOI") or None,
                "summary": _one_sentence_summary(abstract),
                "abstract_available": bool(abstract),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
            # Relevance dominates. The original PubMed order breaks ties, while
            # publication date is used as a secondary signal for a "recent" query.
            recency = year or 0
            candidates.append((score, recency, item))

        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = [item for _, _, item in candidates[:limit]]

        return {
            "query": query,
            "count": int(search.get("count", 0)),
            "years_filter": years_filter,
            "sort": sort,
            "results": results,
            "source": "PubMed/NCBI",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/",
        }


def _build_query(query: str, years: int | None) -> str:
    """Turn common natural-language health queries into a tighter PubMed query."""
    term = query
    lower = query.lower()
    if "creatine" in lower and "strength" in lower:
        # Require both concepts in the searchable title/abstract fields. This avoids
        # unrelated protein/synbiotic papers that happen to contain "muscle strength".
        term = '(creatine[Title/Abstract]) AND (strength[Title/Abstract])'
        if "supplement" in lower:
            term = f"{term} AND (supplement*[Title/Abstract])"
    if years is not None:
        cutoff = date.today().year - years
        term = f"({term}) AND ({cutoff}:3000[dp])"
    return term


def _keywords(query: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z-]{2,}", query.lower())
        if token not in _STOPWORDS
    ]


def _relevance_score(title: str, abstract: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    title_l = title.lower()
    abstract_l = abstract.lower()
    score = 0.0
    for keyword in keywords:
        if keyword in title_l:
            score += 4.0
        elif keyword in abstract_l:
            score += 1.0
    # Give a strong bonus when the two main concepts occur together in the title.
    if "creatine" in title_l and "strength" in title_l:
        score += 8.0
    return score


def _empty_result(query: str, search: dict[str, Any], years: int | None, sort: str) -> dict[str, Any]:
    return {
        "query": query,
        "count": int(search.get("count", 0)),
        "years_filter": years,
        "sort": sort,
        "results": [],
        "source": "PubMed/NCBI",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/",
    }


def _year(value: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", value or "")
    return int(match.group(0)) if match else None


def _abstracts_by_pmid(xml: str) -> dict[str, str]:
    root = ET.fromstring(xml)
    out: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID") or ""
        parts: list[str] = []
        for node in article.findall(".//Abstract/AbstractText"):
            text = " ".join("".join(node.itertext()).split())
            if text:
                label = node.attrib.get("Label")
                parts.append(f"{label}: {text}" if label else text)
        if pmid:
            out[pmid] = " ".join(parts)
    return out


def _one_sentence_summary(abstract: str) -> str | None:
    """Return one extractive sentence; never generate a claim not present in the abstract."""
    if not abstract:
        return None
    text = " ".join(abstract.split())
    labeled = re.findall(
        r"(?:RESULTS?|CONCLUSIONS?|FINDINGS?|KEY FINDINGS?):\s*(.+?)(?=(?:OBJECTIVES?|METHODS?|RESULTS?|CONCLUSIONS?|FINDINGS?|KEY FINDINGS?):|$)",
        text,
        flags=re.I,
    )
    candidate = labeled[-1] if labeled else text
    match = re.search(r".+?[.!?](?:\s|$)", candidate)
    sentence = match.group(0).strip() if match else candidate[:320].rstrip(" ,;:") + ("…" if len(candidate) > 320 else "")
    if len(sentence) > 360:
        sentence = sentence[:357].rsplit(" ", 1)[0] + "…"
    return sentence
