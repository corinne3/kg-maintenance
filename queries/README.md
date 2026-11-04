# The same question in Cypher and in SPARQL

Question: *"For engine-driven pumps (EDP), which conditions are reported, and how often?"*

## Cypher (property graph: Neo4j, FalkorDB, Memgraph…)

```cypher
MATCH (p:PartType {key: 'ENGINE_DRIVEN_PUMP'})<-[:INVOLVES_PART]-(r:Report)-[:HAS_CONDITION]->(c:Condition)
RETURN c.label AS condition, count(DISTINCT r) AS reports
ORDER BY reports DESC
```

## SPARQL (RDF: Oxigraph, GraphDB, Jena, rdflib…)

```sparql
PREFIX kg: <http://example.org/kg#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?condition (COUNT(DISTINCT ?r) AS ?reports) WHERE {
  ?r kg:INVOLVES_PART kg:PartType_ENGINE_DRIVEN_PUMP ;
     kg:HAS_CONDITION ?c .
  ?c rdfs:label ?condition .
}
GROUP BY ?condition
ORDER BY DESC(?reports)
```

## Provenance: "where does this link come from?"

Cypher: provenance is a property of the relationship.

```cypher
MATCH (r:Report)-[i:INVOLVES_PART]->(p:PartType {key: 'ENGINE_DRIVEN_PUMP'})
RETURN r.key, i.source, i.evidence LIMIT 10
```

SPARQL: you have to go through the reified triple (`rdf:Statement`).

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

## Takeaways

| | Property graph (Cypher) | RDF (SPARQL) |
| --- | --- | --- |
| Reading a simple query | Very readable: the `()-[]->()` pattern looks like the drawing | Readable, more verbose |
| Provenance of a link | A property of the relationship | The triple must be reified (or use RDF 1.2 triple terms) |
| Identifiers | Local to the database | Global URIs: can link to public reference data (e.g. ESCO for HR) |
| Ontology, reasoning | Flexible schema, little formal semantics | RDFS / OWL, SHACL validation, inference |
| When to choose it | Applications, exploration, fast GraphRAG | Interoperability, shared reference data, governance |

`run_sparql.py` runs these SPARQL queries on `outputs/graph.ttl`.
For Cypher: load `outputs/property_graph/*.csv` into Neo4j Desktop or FalkorDB and run `outputs/property_graph/import_neo4j.cypher`.
