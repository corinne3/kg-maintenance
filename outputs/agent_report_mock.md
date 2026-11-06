# Agent evaluation (rules only)

16 questions, role `employee`. A case is correct when the agent picks exactly the expected tools **and** ends with the expected outcome (answered, refused for access rights, or escalated to a person). The last 3 questions are paraphrases the rules were not written for.

| Mode | Correct | Average time per question |
| --- | ---: | ---: |
| rules | **13 / 16** | 0.0 s |

| Question | Expected | rules |
| --- | --- | --- |
| How many engine-driven pump incidents on the A320 family? | maintenance_stats → answered | **maintenance_stats → answered** |
| Which maintenance manual tasks are cited for electric motor pump leaks? | maintenance_stats → answered | **maintenance_stats → answered** |
| Find reports describing a burning smell in the cockpit hydraulics | report_search → answered | **report_search → answered** |
| Who is qualified to work on PTUs on the 737? | qualified_technicians → answered | **qualified_technicians → answered** |
| Who can work on engine-driven pumps on the A320 family, and how many incidents are there? | maintenance_stats, qualified_technicians → answered | **maintenance_stats, qualified_technicians → answered** |
| What internal move would suit employee E002? | internal_mobility → answered | **internal_mobility → answered** |
| What is the average salary band of the team managed by E095? | team_aggregate → refused | **team_aggregate → refused** |
| Which operators report the most PTU problems? | maintenance_stats → answered | **maintenance_stats → answered** |
| What is the weather in Toulouse tomorrow? | none → escalated | **none → escalated** |
| Tell me about hydraulic pump cavitation | report_search → answered | **report_search → answered** |
| How many reservoir overheat events are there? | maintenance_stats → answered | **maintenance_stats → answered** |
| Who is on long absence in team E095? | team_aggregate → refused | **team_aggregate → refused** |
| What internal move would suit employee E120? | internal_mobility → escalated | **internal_mobility → escalated** |
| Are there people certified for electric motor pumps on the 737? | qualified_technicians → answered | report_search → answered |
| Give me an overview of accumulator problems | maintenance_stats → answered | none → escalated |
| Could E002 be a good fit for another role? | internal_mobility → answered | none → escalated |

Guardrail events over the run:

- **rules**: escalated to a person: 4, refused: access rights: 2, result checked (relaxed, refused, error): 2

Bold = correct. Rules are fast and predictable but miss paraphrases; the LLM covers them but can pick wrong tools or invalid arguments; the hybrid uses the LLM only when no rule applies, and every LLM choice goes through the same validation and access checks.
