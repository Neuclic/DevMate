# Skills Directory

This project now uses an official-style skill layout that is compatible with the common `SKILL.md` pattern used by deepagents and Anthropic-style skills repositories.

## Layout

Each skill lives in its own folder:

```text
.skills/
  build-static-site/
    SKILL.md
  package-docker-delivery/
    SKILL.md
```

## SKILL.md expectations

- Optional frontmatter with fields such as `name`, `description`, `keywords`, and `tools`
- A `# Skill Name` heading
- A `## Summary` section
- A `## Steps` section
- Optional supporting markdown or text files in the same folder

## Runtime behavior

- The registry searches skill metadata first.
- The agent can then load the full `SKILL.md` content for the best-matching skill.
- Supporting `.md` and `.txt` files are included when full skill context is requested.