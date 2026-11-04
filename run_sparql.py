"""Query the RDF graph with SPARQL.

    pip install rdflib
    python run_step1.py      # writes outputs/graph.ttl
    python run_sparql.py
"""
from pathlib import Path

from rdflib import Graph

TTL = Path(__file__).resolve().parent / "outputs" / "graph.ttl"

QUERIES = {
    "Conditions reported for engine-driven pumps (EDP)": """
        PREFIX kg: <http://example.org/kg#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?condition (COUNT(DISTINCT ?r) AS ?reports) WHERE {
          ?r kg:INVOLVES_PART kg:PartType_ENGINE_DRIVEN_PUMP ;
             kg:HAS_CONDITION ?c .
          ?c rdfs:label ?condition .
        } GROUP BY ?condition ORDER BY DESC(?reports) LIMIT 8
    """,
    "Provenance of report -> EDP links (5 examples)": """
        PREFIX kg: <http://example.org/kg#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?r ?source ?evidence WHERE {
          ?a rdf:type rdf:Statement ;
             rdf:predicate kg:INVOLVES_PART ;
             rdf:object kg:PartType_ENGINE_DRIVEN_PUMP ;
             rdf:subject ?r ;
             kg:source ?source ;
             kg:evidence ?evidence .
        } LIMIT 5
    """,
    "Aircraft families with the most EDP reports": """
        PREFIX kg: <http://example.org/kg#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?family (COUNT(DISTINCT ?r) AS ?reports) WHERE {
          ?r kg:INVOLVES_PART kg:PartType_ENGINE_DRIVEN_PUMP ;
             kg:CONCERNS ?aircraft .
          ?aircraft kg:IS_MODEL ?m .
          ?m rdfs:label ?family .
        } GROUP BY ?family ORDER BY DESC(?reports) LIMIT 8
    """,
}

if __name__ == "__main__":
    g = Graph()
    g.parse(TTL, format="turtle")
    print(f"{len(g)} triples loaded from {TTL.name}\n")
    for title, q in QUERIES.items():
        print(f"== {title}")
        for row in g.query(q):
            print("  ", " | ".join(str(x) for x in row))
        print()
