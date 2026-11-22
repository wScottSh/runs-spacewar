# Domain docs

How the engineering skills read this repo's domain documentation. The repo is single-context: one `GLOSSARY.md` and one `docs/adr/` at the root.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root: this repo's glossary.
- **`../.github/GLOSSARY.md`**, the EGS vocabulary, one level above the repo root (outside this repo). Where this repo's docs disagree with it, it governs, unless the user has said otherwise more recently.
- **`docs/adr/`**: the ADRs that touch the area you are about to work in.

When one of these is missing, work on without it. The `/domain-modeling` skill creates them when a term or decision gets resolved.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as `GLOSSARY.md` defines it, and pass over the synonyms its _Avoid_ lines list.

A concept the glossary lacks is a signal: either you are inventing language the project doesn't use (reconsider), or there is a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

When your output contradicts an existing ADR, say so explicitly:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
