# Décisions de conception

Chaque choix est noté avec les options, l'argument, et **ma décision (Corinne)**.
Le code n'est que l'application de ces décisions.

---

## Décisions prises

### D1 — Périmètre : chapitre ATA 29 (hydraulique), FAA SDR 2025
- Options : ATA 29 seul (514 rapports) · ATA 29 + 32 train (~3× plus) · famille A320 tous chapitres.
- Choix : **ATA 29 seul**.
- Arguments : taille compatible avec un LLM sur CPU (une nuit) ; Airbus et Boeing comparables (200 / 190 rapports) ; contient le cas des pompes.
- Mon pourquoi : _à écrire_

### D2 — Granularité des pièces : type normalisé
- Options : type normalisé · numéro de pièce · les deux.
- Choix : **type normalisé** (ex. « Pompe entraînée par le moteur » regroupe EDP, ENG PUMP, ENGINE DRIVEN PUMP…).
- Arguments : le numéro de pièce manque dans 59 % des rapports ; c'est l'entity resolution qu'on veut démontrer.
- Mon pourquoi : _à écrire_

### D3 — Modèle de graphe : property graph ET RDF, comparés
- Choix : **les deux**, à partir des mêmes faits (`kgcore/facts.py`).
- Arguments : montrer la différence concrète (provenance, verbosité, interopérabilité) plutôt que la réciter.
- Mon pourquoi : _à écrire_

---

## Décisions ouvertes (à trancher)

### D4 — ACMP (Boeing, Bombardier) et EMDP / ELEC PUMP : un seul type ?
- Option A (actuelle) : un seul type « pompe à moteur électrique ». Simple, et la fonction est la même.
- Option B : deux types. Fidèle au vocabulaire constructeur, mais coupe les comparaisons Airbus/Boeing.
- Ma décision : _?_

### D5 — Canadair (CNDAIR) et Bombardier (BOMBDR) : fusionner ?
- Les CRJ sont des Canadair devenus Bombardier (puis Mitsubishi). La FAA garde deux codes.
- Option A (actuelle) : garder deux constructeurs, signaler le lien.
- Option B : fusionner sous « Bombardier ». Plus juste pour l'analyse, mais on perd la trace de la source.
- Ma décision : _?_

### D6 — Les hubs : comment parcourir le graphe pour un GraphRAG ?
- Constat : à 3 sauts depuis « EDP », un parcours naïf ramène 61 % du graphe ; bloquer les hubs ne le réduit qu'à ~55 %.
- Option A : parcours guidé par le schéma (requêtes typées) — ce qui marche à l'étape 1.
- Option B : bloquer les hubs au-delà d'un seuil (50 voisins ?).
- Option C : pondérer les nœuds (un hub vaut moins qu'un nœud rare).
- Ma décision : _?_

### D7 — « Le rapport cite une pièce » ≠ « la pièce est en panne »
- Constat : 12 rapports « PUMP » citent plusieurs pompes ; certaines sont seulement « coupées » ou « vérifiées ».
- Option A (actuelle) : une seule relation `INVOLVES_PART`.
- Option B : deux relations, `HAS_FAULTY_PART` et `MENTIONS_PART`, remplies par le LLM à l'étape 2.
- Ma décision : _?_

### D8 — Les 55 valeurs de `PartName` non reconnues (101 rapports)
- Exemples : `ELEC CONNECTOR`, `MODULE`, `VALVE`, `FUSE`, `SWITCH`, `INDICATOR`…
- Question : les ajouter à l'ontologie, les regrouper (« composant électrique »), ou les ignorer ?
- Ma décision : _?_

---

## Journal de constats (ce que j'ai vu en lançant le code)

- _date — constat_
