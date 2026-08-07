# Translations

English is the normative source. Every page under `docs/site/` is written in
English, and a translation is a copy of one that says the same thing in another
language.

## The structure

```
docs/site/i18n/
├── README.md          # this file
├── locales.md         # which locales exist, and who maintains each
└── <locale>/          # e.g. pt-BR/, de/, ja/
    ├── quickstart/index.md
    ├── deployment/index.md
    ├── security/index.md
    ├── evaluation/index.md
    └── contributing/index.md
```

A locale directory mirrors the site's authored tree, path for path. A page that
does not exist in a locale falls back to English rather than 404ing — a partial
translation is more useful than none, and a reader who hits an English page knows
exactly what happened.

## What is translatable

**The authored pages**, and only those: quickstart, deployment, security,
evaluation, contributing, and the site index.

**Not the generated reference.** Capabilities, integrations, and configuration
are produced from declarations in the code, and those declarations are in English
because every identifier, docstring, and comment in this repository is. A
translated copy would be stale the day after the next capability lands, and there
is no mechanism that could keep it current.

**Not the console's interface strings.** Those live in `surfaces/console/i18n.py`
as keyed messages, and are translated there rather than here — a message is
looked up by key at render time, which a Markdown file cannot do.

## Adding a locale

1. Create `docs/site/i18n/<locale>/` using the BCP 47 tag: `pt-BR`, `de`, `ja`.
2. Copy the authored page you are starting with, preserving its path.
3. Translate the prose. Leave code blocks, command names, setting names, and file
   paths exactly as they are — `NINJASRE_DATABASE_URL` is an identifier, not a
   word, and a translated one does not work.
4. Add a row to `locales.md` naming the locale and who maintains it.

## Keeping a translation honest

A translation of a page that has since changed is worse than no translation: it
tells a reader something that was true. So each translated page carries the
source it was translated from, at the top:

```markdown
<!-- translated-from: quickstart/index.md@<git sha> -->
```

The build reports a translated page whose source has moved since that commit, so
"this page is behind" is something a maintainer is told rather than something a
reader discovers.

If you would rather remove a stale translation than update it, do that. English
is always there behind it.
