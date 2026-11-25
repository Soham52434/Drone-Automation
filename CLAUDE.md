# CLAUDE.md

Claude Code entry point. The project guidelines live in the Cursor files below and are used as-is.

@AGENTS.md
@.cursor/rules/drone-security-agent.mdc

## Skill

Load the `drone-security-agent` skill (`.claude/skills/drone-security-agent/`, a verbatim copy of `.cursor/skills/drone-security-agent/`) before any coding, refactor, test, architecture, or feature work.

When the Cursor skill changes, re-sync the copy:

```bash
rm -rf .claude/skills/drone-security-agent && cp -r .cursor/skills/drone-security-agent .claude/skills/
```
