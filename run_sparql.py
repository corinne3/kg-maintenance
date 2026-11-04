"""Interroger le graphe RDF en SPARQL (à lancer sur ton PC).

    pip install rdflib
    python run_step1.py      # produit outputs/graphe.ttl
    python run_sparql.py
"""
from pathlib import Path

from rdflib import Graph

TTL = Path(__file__).resolve().parent / "outputs" / "graphe.ttl"

QUERIES = {
    "États déclarés pour les pompes moteur (EDP)": """
        PREFIX kg: <http://example.org/kg#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?etat (COUNT(DISTINCT ?r) AS ?rapports) WHERE {
          ?r kg:INVOLVES_PART kg:PartType_ENGINE_DRIVEN_PUMP ;
             kg:HAS_CONDITION ?c .
          ?c rdfs:label ?etat .
        } GROUP BY ?etat ORDER BY DESC(?rapports) LIMIT 8
    """,
    "Provenance des liens rapport -> EDP (5 exemples)": """
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
    "Familles d'avions avec le plus de rapports EDP": """
        PREFIX kg: <http://example.org/kg#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?famille (COUNT(DISTINCT ?r) AS ?rapports) WHERE {
          ?r kg:INVOLVES_PART kg:PartType_ENGINE_DRIVEN_PUMP ;
             kg:CONCERNS ?avion .
          ?avion kg:IS_MODEL ?m .
          ?m rdfs:label ?famille .
        } GROUP BY ?famille ORDER BY DESC(?rapports) LIMIT 8
    """,
}

if __name__ == "__main__":
    g = Graph()
    g.parse(TTL, format="turtle")
    print(f"{len(g)} triplets chargés depuis {TTL.name}\n")
    for title, q in QUERIES.items():
        print(f"== {title}")
        for row in g.query(q):
            print("  ", " | ".join(str(x) for x in row))
        print()
