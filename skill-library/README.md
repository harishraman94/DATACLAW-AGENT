# Skill Library

Community-contributed skills for Dataclaw. Users can browse and install these from the Skills page in the UI.

## Contributing a skill

1. Create a `.md` file in this directory
2. Add YAML frontmatter with `name`, `description`, and `tags`
3. List other skill dependencies upfront: a `**Related skills:**` line as the first body line (see Format), naming each skill this one hands off to, escalates to, or is fetched by, with a short parenthetical role. Omit the line only if the skill genuinely stands alone.
4. Write the skill instructions in the body

### Format

```markdown
---
name: my_skill
description: Short description of what this skill does
tags: [category1, category2]
---

**Related skills:** `other_skill` (what it is used for), `another_skill` (its role).

Skill instructions go here. These are injected into the agent's
system prompt when the skill is active.
```

### Guidelines

- Keep skill names lowercase with underscores (they become the filename)
- List other skill dependencies upfront in a `**Related skills:**` line at the top, so the interdependence graph is explicit rather than buried in prose
- Write clear, actionable instructions the agent can follow
- Use tags to help users find relevant skills
- Test your skill before submitting
