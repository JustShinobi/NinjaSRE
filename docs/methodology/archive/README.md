# Archived methodology skills

One directory per vendor, each holding the `SKILL.md` that used to live under
`capabilities/skills/<vendor>/` while that vendor's integration package was
installed. The frontmatter is untouched: `directs_tools` and
`requires.integrations` still name exactly what they named the day the
package left, which is what lets the skill return whole.

**Why archived rather than deleted.** The methodology a skill encodes —
which call to make first, what a vendor's own quirks mean for the answer, the
order that turns a big result into a small one — outlives whether the vendor
happens to be in the catalogue this month. Keeping the text is cheaper than
re-deriving it, and re-deriving it from nothing is what actually happens to a
deleted skill.

**Why not under `capabilities/skills/`.** Discovery walks every `SKILL.md`
under that root and validates what it finds: a skill whose `directs_tools`
names a tool no package declares, or whose `requires.integrations` names an
integration nothing installs, fails the capability catalogue's own build. A
vendor's skill only validates while the vendor's package is installed, so an
archived skill has to sit somewhere discovery does not reach.

**How a skill comes back.** Move its directory back under
`capabilities/skills/`, alongside the vendor's package returning to
`integrations/` and its synthetic scenario returning to
`tests/synthetic/integration_scenarios/`. Nothing in the frontmatter needs to
change for that to work — that is the whole point of preserving it as-is.
