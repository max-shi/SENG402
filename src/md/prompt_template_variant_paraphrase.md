# RQ3 generation prompt — variant V3 (paraphrased)

Prompt-sensitivity test variant. Same semantic instructions as
`prompt_template.md`, deliberately reworded — different task framing, verb
choices, and sentence structure — to isolate wording sensitivity from
content sensitivity. Loaded by `rq3_prompt_sensitivity.py`, same
last-fence-marker extraction convention as `prompt_template.md`.

```
Imagine you are a contributor drafting documentation for an open-source
library that currently has none.

Package: {package_name}
Ecosystem: {ecosystem}

You have access to the library's complete public interface below: every
exported class and function, along with parameter names and, where known,
their types and return types. Nothing else is available to you — no
docstrings, no inline comments, no source code bodies.

```
{api_surface}
```

Based solely on what's shown above, produce a README for this project. It
should contain:
- A brief opening that explains, in your own words, what this library
  appears to be designed to do, inferred entirely from its interface.
- A walkthrough of the key classes and functions and how they fit together.
- At least one plausible code example demonstrating typical usage.

Write it as a finished document ready to drop into the repository directly.
Do not add any framing or disclaimers, do not acknowledge that this was
generated from signatures alone, and do not mention that an AI wrote it.
```
