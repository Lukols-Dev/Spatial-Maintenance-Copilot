# smc-agent

The agent of the localisation loop: a LangGraph graph over `smc_core`, with a language model on Amazon
Bedrock: Amazon Nova 2 Lite through the Converse API (`nova.py`), or Claude through the Messages API
(`bedrock.py`). Both answer in the Messages API's blocks, the shape the agent keeps its history in.

```
START -> localise -> (reliable?) -> present -> await_approval -> END
                 \-> (not reliable) -> guide -> await_view -> localise
```

- **localise** asks the `Perception` (in the service: the workspace, by the code `/localise` runs) for a
  viewpoint and the policy's decision on it. The branch is that decision, never the model's.
- **guide** and **present** are the model's turns. It explains the decision and acts through the tools of
  its branch: `suggest_viewpoints` and `request_view` when the result is not reliable, `present_result`
  when it is. Guards hold its output to the policy: another move than the policy's, numbers in its words,
  or a viewpoint that does not exist are replaced or dropped, and recorded as `guard` events.
- **await_view** and **await_approval** stop the graph (`interrupt`) until the operator answers. The
  checkpointer keeps the session between calls, so each answer can come in another HTTP request.

When the model gives no answer (no region set, Bedrock unreachable, a refusal, or no ending tool within
`MAX_MODEL_CALLS`) the operator gets the policy's own words and the trace records a `fallback` event, so a
session never waits for the model. The model's history is only ever appended, as the thinking blocks of
Claude Opus 5.5 require; Nova's reasoning comes back redacted and is not kept.

`Copilot.start / choose_view / approve / trace / turn` is the whole API. The tests (`tests/`) run the
graph against a scripted model and a perception with fixed answers; nothing reaches AWS.
