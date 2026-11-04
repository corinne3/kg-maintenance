# Étape 2 — Extraction par LLM (llama3.2:3b)

- Rapports traités : **122**
- Temps moyen par rapport : **20.0 s**
- Sorties JSON invalides : **0**
- Types de pièces inventés (hors liste fermée) : **21** (`PUMP_CONNECTOR` ×2, `HYD 3 LO PRESS` ×2, `ACMP 3A HYD PUMP` ×2, `MLG TIRE` ×2, `HYDRAULIC LINE` ×2, `PRESSURE_SWITCH S29` ×1)
- Tâches AMM citées par le LLM mais absentes du texte : **2 / 45** (ex. `29-11-51` dans AALA202501247485, `29-12-51-000-001-A` dans DALA2025100607266)
- Accord avec le champ structuré (quand il est précis) : **2 / 4**

## Les rapports « PUMP » : quelle pompe est en panne selon le LLM ?

| Réponse du LLM | Rapports |
| --- | ---: |
| ENGINE_DRIVEN_PUMP | 68 |
| AUCUNE_PRECISE | 37 |
| ELECTRIC_MOTOR_PUMP | 6 |
| PLUSIEURS | 6 |

## Comparaison à la référence (20 rapports « PUMP »)

Référence : `data/ground_truth.xlsx` — annotateur : Claude (AI), not a human expert.

| Rapport | Référence | Dictionnaire | LLM |
| --- | --- | --- | --- |
| `SWAA2025032007746` | SEVERAL | **SEVERAL** | ENGINE_DRIVEN_PUMP |
| `DALA2025032402192` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** |
| `YENA2025052700542` | NO_PUMP_FAILED | SEVERAL | ENGINE_DRIVEN_PUMP |
| `GTIA2025052738929` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** |
| `GTIA2025060238935` | NO_PUMP_FAILED | SEVERAL | ENGINE_DRIVEN_PUMP |
| `HALA20250609169` | NO_PUMP_FAILED | SEVERAL | **NO_PUMP_FAILED** |
| `BAGA2025092900009` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** |
| `HALA20251017321` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** |
| `SWAA2025102728412` | SEVERAL | **SEVERAL** | **SEVERAL** |
| `SWAA2025102729004` | SEVERAL | **SEVERAL** | **SEVERAL** |
| `CALA2025111811319` | ELECTRIC_MOTOR_PUMP | SEVERAL | NO_PUMP_FAILED |
| `JJBA20251222028` | ELECTRIC_MOTOR_PUMP | SEVERAL | **ELECTRIC_MOTOR_PUMP** |
| `CALA2025101510127` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `IPXA2025021782873` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `AALA202501247485` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `YEN2025F00010` | NO_PUMP_FAILED | **NO_PUMP_FAILED** | ENGINE_DRIVEN_PUMP |
| `SWAA2025050768343` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | SEVERAL |
| `QR9R2025050700001` | CANNOT_TELL | NO_PUMP_FAILED | NO_PUMP_FAILED |
| `AALA202504229338` | ELECTRIC_MOTOR_PUMP | **ELECTRIC_MOTOR_PUMP** | NO_PUMP_FAILED |
| `AALA202503036126` | NO_PUMP_FAILED | **NO_PUMP_FAILED** | **NO_PUMP_FAILED** |

- Dictionnaire : **10 / 19** conformes à la référence.
- LLM : **12 / 19** conformes (sur les rapports déjà traités par le LLM).
- `CANNOT_TELL` dans la référence = non compté.
- Limite : la référence est un LLM (Claude), pas un expert maintenance. Dans un vrai projet, un échantillon serait validé par les mécaniciens.
