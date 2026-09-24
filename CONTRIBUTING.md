# Contributing

Thanks for wanting to add a skill. The bar for this repository is simple: **a skill here must have been used for real work at least once.** Speculative architecture is not a skill.

---

## Add a skill

1. Fork the repository and create a branch.
2. Add your skill as `skills/<skill-name>/`.
3. Make sure it passes the checklist below.
4. Open a pull request describing **what task the skill was used on** and what went wrong before the skill existed.

Prefer lowercase `kebab-case` directory names. The directory name and the `name:` in frontmatter should match.

---

## Required files

```
skills/my-skill/
├── SKILL.md          ← required
├── README.md         ← required for this repository
└── LICENSE           ← required if it differs from MIT
```

### `SKILL.md`

Frontmatter must contain `name` and `description`. The description is the *only* text an agent sees when deciding whether to load the skill, so it must say both what the skill does and when to invoke it:

```markdown
---
name: my-skill
description: Does X for Y. Use this skill when the user asks for A, B or C.
  Triggers on phrases like "…", "…", "…".
---
```

Write the trigger phrases in the language your users actually type — including Chinese, if that is how the request arrives.

The body is instructions for an agent, not marketing copy. Cover:

- **When to invoke / not invoke** — including the neighbouring tasks that belong to another skill
- **The workflow**, phase by phase, with the exact commands to run
- **Constraints that are easy to get wrong** — the ones that silently produce bad output
- **Pitfalls you hit yourself**, each with a symptom and a fix
- **What the skill does not do**, so it does not get over-applied

### `README.md`

Human-facing: what the problem is, prerequisites, a copy-pasteable quick start, the file layout, and screenshots or sample output if the result is visual.

---

## Checklist before opening the PR

- [ ] `SKILL.md` frontmatter has `name` and `description`, and the description names the trigger situations
- [ ] Every command in the docs was run at least once — no invented flags
- [ ] Scripts compile and run from a clean checkout (`python3 -m py_compile`, `bash -n`, `node --check`)
- [ ] No secrets, tokens, private hostnames/IPs, or personal absolute paths in any committed file
- [ ] No private data: sample inputs are synthetic or explicitly shareable
- [ ] Generated artifacts (renders, PDFs, build output) are gitignored; only small documentation images are committed
- [ ] The README states prerequisites and third-party services the skill depends on
- [ ] `LICENSE` present at the skill root, or the repository MIT license applies

---

## Style

- Keep instructions imperative and specific: "run `python3 scripts/x.py --all`", not "generate the pages".
- Prefer tables for inventories and decision rules; they survive context compression better than prose.
- Document the *reason* behind a rule when it is non-obvious — an agent that understands why a constraint exists will not route around it.
- Keep skills self-contained. A skill may reference files inside its own directory; it must not depend on a sibling skill's internals.

---

## Reporting problems

Open an issue with the skill name, what you asked for, what the agent did, and any command output. If you found a pitfall that is not documented in `SKILL.md`, that is exactly the kind of issue worth filing — or better, the kind of pull request worth sending.

---

## License

By contributing, you agree that your contribution is licensed under the MIT license in [`LICENSE`](LICENSE).
