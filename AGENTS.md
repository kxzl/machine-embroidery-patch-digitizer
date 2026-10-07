# AGENTS.md

## Subagents

- **Default subagent model:** `opencode/space-bunny-free`.
- **Fallback on API / rate-limit error:** retry the subagent with
  `opencode/deepseek-v4.1-flash`.
- Use any other model only when the operator explicitly asks for it.
