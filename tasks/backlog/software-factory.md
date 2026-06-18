# Software Factory (Spec + Tests → Agent-Built Code)

**What:** Specialization where humans write specs + scenario validations and agents
generate/iterate implementation until tests pass at a satisfaction threshold.
End state: repo of specs + test harnesses, code is the agent's job.

**Why deferred:** Large, and a different specialization of the core loop than v1's
analyze→propose domain. Build the loop first, then point it at code.

**Value:** The "1000x engineer" path — one builder surrounded by a system of agents.

**v1 preparation (already in v1):** The loop (capture→analyze→propose→gate→improve)
and the action/risk + audit primitives are exactly what a factory reuses; spec and
test results are just another artifact type.

**Adds later:** spec format, test-harness runner, generate-and-iterate executor,
probabilistic satisfaction threshold. Keep human review on the spectrum, not zero.

**Effort:** XL
