# Local Developer Profiles

This folder contains **personal developer profiles** for LLM agent configuration.

## What Is This?

Each developer can create a personal `.mdc` rule file here to tell agents:
- What OS and shell they use (Windows/PowerShell, macOS/zsh, Linux/bash)
- What language to communicate in (Russian, English)
- Personal preferences for agent behavior (verbosity, confirmation prompts)

## Why Is This Folder Gitignored?

Personal profiles are **machine-specific** — they should not be shared with the team.
Only this `README.md` is committed. Your `.mdc` profile files stay local.

## How to Create Your Profile

1. Copy the template:
   ```
   .cursor/templates/developer-profile.mdc  →  .cursor/rules/local/my-profile.mdc
   ```
2. Open `my-profile.mdc` and fill in your settings
3. Cursor will automatically apply it in every session

For detailed instructions, see [`docs/developer-setup.md`](../../../docs/developer-setup.md).

## Example Profile Names

```
.cursor/rules/local/
  my-profile.mdc          ← your personal profile (gitignored)
  work-laptop.mdc         ← profile for work machine (gitignored)
```

## What NOT to Put Here

- API keys or secrets → use `.env`
- Project-wide rules → use `.cursor/rules/` (committed)
- Temporary overrides for a specific feature → use inline comments
