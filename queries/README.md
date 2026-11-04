# La même question, en Cypher et en SPARQL

Question : *« Pour les pompes moteur (EDP), quels états sont déclarés, et combien de fois ? »*

## Cypher (property graph : Neo4j, FalkorDB, Memgraph…)

```cypher
MATCH (p:PartType {key: 'ENGINE_DRIVEN_PUMP'})<-[:INVOLVES_PART]-(r:Report)-[:HAS_CONDITION]->(c:Condition)
RETURN c.label AS etat, count(DISTINCT r) AS rapports
ORDER BY rapports DESC
```

## SPARQL (RDF : Oxigraph, GraphDB, Jena…)

```sparql
PREFIX kg: <http://example.org/kg#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?etat (COUNT(DISTINCT ?r) AS ?rapports) WHERE {
  ?r kg:INVOLVES_PART kg:PartType_ENGINE_DRIVEN_PUMP ;
     kg:HAS_CONDITION ?c .
  ?c rdfs:label ?etat .
}
GROUP BY ?etat
ORDER BY DESC(?rapports)
```

## Provenance : « d'où vient ce lien ? »

Cypher : la provenance est une propriété de la relation.

```cypher
MATCH (r:Report)-[i:INVOLVES_PART]->(p:PartType {key: 'ENGINE_DRIVEN_PUMP'})
RETURN r.key, i.source, i.evidence LIMIT 10
```

SPARQL : il faut passer par le triplet réifié (`rdf:Statement`).

```sparql
PREFIX kg: <http://example.org/kg#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?r ?source ?evidence WHERE {
  ?a rdf:type rdf:Statement ;
     rdf:predicate kg:INVOLVES_PART ;
     rdf:object kg:PartType_ENGINE_DRIVEN_PUMP ;
     rdf:subject ?r ;
     kg:source ?source ;
     kg:evidence ?evidence .
} LIMIT 10
```

## Ce qu'il faut retenir

| | Property graph (Cypher) | RDF (SPARQL) |
| --- | --- | --- |
| Lire une requête simple | Très lisible : le motif `()-[]->()` ressemble au dessin | Lisible, mais plus verbeux |
| Provenance d'un lien | Propriété de la relation, naturelle | Il faut réifier le triplet (ou RDF 1.2 / RDF-star) |
| Identifiants | Locaux à la base | URI globales : on peut relier à des référentiels publics (ex. ESCO en RH) |
| Ontologie, raisonnement | Schéma souple, peu de sémantique formelle | RDFS / OWL, contrôles SHACL, inférence |
| Quand le choisir | Application, exploration, GraphRAG rapide | Interopérabilité, référentiels partagés, gouvernance |

`run_sparql.py` (à la racine) exécute ces requêtes SPARQL sur `outputs/graphe.ttl`.
Pour le Cypher : charger `outputs/property_graph/*.csv` dans Neo4j Desktop ou FalkorDB (voir `docs/COMPRENDRE.md`).
