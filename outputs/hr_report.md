# HR domain — Results

Scope: a **synthetic** aerospace company of 161 employees (Toulouse in French, Bristol in English), linked to the real **ESCO v1.2.1** taxonomy (European Commission). No real person. Same `kgcore/` as the maintenance case.

## 1. The reference taxonomy is ambiguous too

- ESCO occupation labels (English + French, preferred + alternative): **48,059**, of which **1,539 (3%)** point to more than one occupation.
- ESCO skill labels: **119,830**, of which **748** point to more than one skill.
- Examples: "responsable des ressources humaines" is the French preferred label of *human resources officer* and an alternative label of *human resources manager*. "Technicien **en** maintenance aéronautique" and "technicien **de** maintenance aéronautique" are two different ESCO occupations.
- French gendered labels ("ingénieur/ingénieure de données") must be split and rebuilt before matching: a person types one form, the taxonomy stores both in one string.

## 2. Linking job titles and skills to the taxonomy

| Item | Linked to one concept | Ambiguous | Not found |
| --- | ---: | ---: | ---: |
| Job titles (161) | 133 | 14 | 14 |
| Skills written from ESCO labels (966) | 939 | 27 | 0 |
| Vague skills ("teamwork", "IT"…) (322) | 69 | 30 | 223 |

- Linked titles are right 100% of the time, but **14 titles are ambiguous** even when copied from ESCO: `accountant`, `data scientist`, `finance manager`, `mechanical engineer`, `product quality monitor`, `responsable des ressources humaines`.
- Company-specific titles are never found: `AI Product Owner`, `Aircraft Tech`, `Chef de projet SI`, `DRH adjointe`, `Data Platform Engineer`, `Full Stack Dev`, `Ing. qualité`, `Ingé Data`, `Ingénieur Méthodes MRO`, `Licensed B1 Engineer`, `MRO Engineer`, `Mécano avion`. They need a company mapping table, owned by HR.
- Vague skills that *do* match an ESCO label: `communication` (53), `IT` (16). They link, but to very generic concepts: the match is right and useless.

## 3. Garbage nodes and isolated islands

Skills built naively from the raw text (one node per string typed), then linked to ESCO:

| | Raw text only | With ESCO linking |
| --- | ---: | ---: |
| Skill nodes shared by Toulouse and Bristol: meaningful skills | 0 | 120 |
| Skill nodes shared by Toulouse and Bristol: vague skills | 2 | 2 |
| Islands of employees, ignoring vague skills | 12 | 3 |
| Islands that mix both sites | 0 | 3 |

- In the raw graph, the only things connecting the French and English sites are vague words that happen to be spelled the same in both languages ("Excel", "communication"). The graph *looks* connected; it is held together by garbage nodes.
- Remove them and the raw graph falls apart into 12 islands, none spanning both sites. Linking to ESCO, which carries French and English labels for the same concept, reconnects the sites through 120 real skills.
- Most connected raw skill nodes: `communication` (53 employees), `Excel` (44 employees), `travail en équipe` (32 employees).

## 4. Human hubs and transitivity bias

- The operations manager sits on 25 of 30 projects and manages every team lead: **66 direct links**, the most connected person in the graph.
- Task: suggest internal moves. A suggestion is *absurd* if the person has **none** of the skills the target job requires (ESCO essential skills).

| Inference | Suggestions (person, job) | Absurd |
| --- | ---: | ---: |
| Colleague of a colleague: "worked on a project with an X, so could become an X" | 336 | 243 (72%) |
| Same, through the human hub only (both on projects with the operations manager) | 880 | 702 (80%) |
| Schema-guided: best match between the person's skills and each job's required skills | 120 | 0 (no suggestion for 12 people with no matching skill) |

- Following links between people transfers *who you know* into *what you can do*. The longer the chain and the more it goes through a hub, the worse it gets.
- The schema-guided path (person → skill ← required by → job) only suggests what the skills support, and it can say "no suggestion". Matches stay partial (on average 11% of the required skills), because each synthetic employee declares only 6 skills: incomplete profiles are a pitfall of their own.

## 5. Access control and inference (sensitive data)

Salary band and long absence are marked `sensitive` on the edge. Edges visible per role:

| Role | Visible edges |
| --- | ---: |
| employee | 1,955 |
| manager | 1,963 |
| hr | 2,124 |

- Hiding sensitive edges is not enough. An "anonymous" aggregate such as *average salary band per team* reveals individuals when a team is small: **13 of 30 teams** have fewer than 5 people, covering **27 employees**.
- The same goes for *number of long absences per team*: 1 of the 8 employees on long absence sit in a team small enough to be identified.
- Rule applied: no aggregate on fewer than 5 people (k-anonymity), enforced in the query layer, not left to each user.

## 6. Change over time

- A reorganisation on 2026-07-01 moved part of a team to a new manager. Without dates on the `REPORTS_TO` edge, **4 employees have two managers**. With validity dates and an "as of 2026-11-06" filter: 0.
- Certifications expire: **12 certified people** hold at least one expired certification. A graph that does not store validity would still call them qualified.

## 7. One graph, two domains

HR certifications and FAA maintenance reports share the same `PartType` and `AircraftModel` nodes, so one query crosses both domains:

> *For engine-driven pumps on the A320 family: how many incidents, and who is qualified to work on them?*

- Maintenance side (real FAA data): **51 incident reports** in 2025.
- HR side (synthetic): **23 qualified technicians** with a valid certification (Toulouse: 17, Bristol: 6); **5 more** would be counted if expiry dates were ignored.
- Same `kgcore/` (facts, graph, exports). The HR domain added one generic module, `kgcore/lexicon.py` (label-based linking to a reference taxonomy), and edge attributes (validity dates, sensitivity).
