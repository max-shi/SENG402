# RQ3 generation prompt

```
You are writing developer documentation for an open-source software library.

Library name: {package_name}
Language/ecosystem: {ecosystem}

Below is the complete public API surface of this library: the signatures of
every public class and function (parameter names, types where available,
return types where available). No docstrings, comments, or implementation
code are included below — this is all the information you have about what
the library does.

```
{api_surface}
```

Using only the information above, write a README-style document for this
library. Include:
- A short introduction describing what the library appears to do, based on
  its API surface.
- An overview of its main classes/functions and how they relate to each
  other.
- One or more realistic usage examples showing how a developer might call
  this API.

Write the README directly, as if it will be published in the project's
repository. Do not mention that you were given only signatures, do not
mention that you are an AI, and do not include any meta-commentary about
the task.

Important: you may already be familiar with this library from your
training data. Do not rely on any prior knowledge of it, and do not let it
influence your answer. Base your answer strictly and only on the API
surface given above — do not mention, reference, or invent any internal
file paths, module names, or implementation details that are not
explicitly shown in the signatures above.
```

**Decided 2026-08-12:** the V4-style disclaimer (last paragraph above) is
now part of the locked template — calibration showed it eliminated
detected leaks for 2 of 3 sensitivity libraries (`pyspellchecker`,
`web-fragments`) with no observed downside, and did nothing for the third
(`xsdata`), i.e. strictly non-negative. No explicit word-length target was
added (V2 testing showed ~500 words reliably halves output length, but
this was left as an open option, not adopted) — output is expected to run
900–2100 words per the V0 baseline, as before.
