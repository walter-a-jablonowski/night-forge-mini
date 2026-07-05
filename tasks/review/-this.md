Five task files created in `tasks/review/`, matching the backlog house style:

| File                     | Effort | When                                                                                                |
| ------------------------ | ------ | --------------------------------------------------------------------------------------------------- |
| `structured-output.md`   | S      | anytime — do first, de-risks the next one                                                           |
| `agentic-analyze.md`     | M→L    | the one real architectural evolution; after structured-output                                       |
| `metric-as-objective.md` | M      | anytime; also the substrate for drift-detection / roi-measurement                                   |
| `sqlite-store.md`        | M      | triggered: when scheduler-daemon or approval-ui adds a second writer                                |
| `core-as-package.md`     | S      | triggered: when a second real installation exists (the `__version__` first step is worth doing now) |

Each file states what it is, why it's deferred or trigger-based, a design sketch that fits the existing seams, and cross-references the related backlog tasks (observability, drift-detection, roi-measurement, run-triggers). Nothing in them requires restructuring the core — that was the point of the review.
