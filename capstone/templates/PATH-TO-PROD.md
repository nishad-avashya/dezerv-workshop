# Path to production: __SQUAD__ (__SERVICE__)

Fill in the blanks. Be concrete: names, owners, dates.

## Real connectors and their owners
| Capability | Mock used in the workshop | Real source | Owner |
|---|---|---|---|
| Logs | CloudWatch `/dezerv/__SERVICE__` | | |
| Records (`__COLLECTION__`) | mongomock over S3 | | |
| Deploy history | `deploys.json` | | |
| Tickets | DynamoDB mock (project PAY) | | |
| Custom tool `__TOOL__` | Lambda over mock data | | |

## Data and telemetry gaps (CTX-05 readiness)
Structured logs with `commit`, `caller` (file:line) and `template_id`? Trace ids? Error-code catalog with owners?
- [ ] 
- [ ] 

## Charter owner and review
Who owns `charter.md`, and how do changes get reviewed?

## Incident-replay set
Workshop set: 3 cases. Target: 30 real, sanitized incidents (EVL-01). Who curates them?

## Region and network
Region(s) required; VPC / PrivateLink needs for the real data sources.

## First L1 action we would allow
(One action beyond "recommend", with its approval rule and rollback.)

## Gate for the real thing
Result in the workshop: __GATE__. What would you tighten before going live?
