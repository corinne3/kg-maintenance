# Step 2 — LLM extraction (llama3.2:3b)

- Reports processed: **122** (of which 117 "PUMP" reports)
- Average time per "PUMP" report: **16.1 s** (CPU only, 8 GB RAM)
- Invalid JSON outputs: **0**
- Responses with at least one part type outside the allowed list: **15 / 122** (12%). Examples: `PUMP_CONNECTOR` ×2, `HYD 3 LO PRESS` ×2, `ACMP 3A HYD PUMP` ×2, `MLG TIRE` ×2, `HYDRAULIC LINE` ×2, `PRESSURE_SWITCH S29` ×1
- Maintenance manual (AMM) references not found in the text: **2 / 45**. They are near-copies of real references, which makes them hard to spot:
    - `AALA202501247485`: LLM wrote `29-11-51`, text says `29-11-11-400-801`
    - `DALA2025100607266`: LLM wrote `29-12-51-000-001-A`, text says `29-12-51`, `29-12-51-400-001-A`

## "PUMP" reports: which pump failed?

| Answer | Dictionary | LLM |
| --- | ---: | ---: |
| ENGINE_DRIVEN_PUMP | 58 | 68 |
| ELECTRIC_MOTOR_PUMP | 18 | 6 |
| POWER_TRANSFER_UNIT | 1 | 0 |
| RAM_AIR_TURBINE | 0 | 0 |
| SEVERAL | 12 | 6 |
| NO_PUMP_FAILED (dictionary: no specific pump found) | 28 | 37 |

## Comparison with the reference (20 "PUMP" reports)

Reference: `data/ground_truth.xlsx`, annotator: Claude (AI), not a human expert.

| Report | Reference | Dictionary | LLM | Hybrid |
| --- | --- | --- | --- | --- |
| `SWAA2025032007746` | SEVERAL | **SEVERAL** | ENGINE_DRIVEN_PUMP | ENGINE_DRIVEN_PUMP |
| `DALA2025032402192` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `YENA2025052700542` | NO_PUMP_FAILED | SEVERAL | ENGINE_DRIVEN_PUMP | ENGINE_DRIVEN_PUMP |
| `GTIA2025052738929` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `GTIA2025060238935` | NO_PUMP_FAILED | SEVERAL | ENGINE_DRIVEN_PUMP | ENGINE_DRIVEN_PUMP |
| `HALA20250609169` | NO_PUMP_FAILED | SEVERAL | **NO_PUMP_FAILED** | **NO_PUMP_FAILED** |
| `BAGA2025092900009` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `HALA20251017321` | ENGINE_DRIVEN_PUMP | SEVERAL | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `SWAA2025102728412` | SEVERAL | **SEVERAL** | **SEVERAL** | **SEVERAL** |
| `SWAA2025102729004` | SEVERAL | **SEVERAL** | **SEVERAL** | **SEVERAL** |
| `CALA2025111811319` | ELECTRIC_MOTOR_PUMP | SEVERAL | NO_PUMP_FAILED | NO_PUMP_FAILED |
| `JJBA20251222028` | ELECTRIC_MOTOR_PUMP | SEVERAL | **ELECTRIC_MOTOR_PUMP** | **ELECTRIC_MOTOR_PUMP** |
| `CALA2025101510127` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `IPXA2025021782873` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `AALA202501247485` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** | **ENGINE_DRIVEN_PUMP** |
| `YEN2025F00010` | NO_PUMP_FAILED | **NO_PUMP_FAILED** | ENGINE_DRIVEN_PUMP | **NO_PUMP_FAILED** |
| `SWAA2025050768343` | ENGINE_DRIVEN_PUMP | **ENGINE_DRIVEN_PUMP** | SEVERAL | **ENGINE_DRIVEN_PUMP** |
| `QR9R2025050700001` | CANNOT_TELL | NO_PUMP_FAILED | NO_PUMP_FAILED | NO_PUMP_FAILED |
| `AALA202504229338` | ELECTRIC_MOTOR_PUMP | **ELECTRIC_MOTOR_PUMP** | NO_PUMP_FAILED | **ELECTRIC_MOTOR_PUMP** |
| `AALA202503036126` | NO_PUMP_FAILED | **NO_PUMP_FAILED** | **NO_PUMP_FAILED** | **NO_PUMP_FAILED** |

- Dictionary: **10 / 19**
- LLM: **12 / 19**
- Hybrid (dictionary when it finds 0 or 1 pump, LLM when it finds several): **15 / 19**
- `CANNOT_TELL` in the reference is not scored. Bold = matches the reference.
- Limits: 19 scored cases, 12 of them chosen because they are ambiguous; the reference is an LLM (Claude), not a maintenance expert. Trends, not proof.
