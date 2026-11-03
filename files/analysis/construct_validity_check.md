# Construct-Validity Check of the 15 Committed LIWC Dimensions

For each committed dimension, this document asks a single question:

> Are the words that LIWC-22 is actually counting in the
> highest-scoring libraries the *kind* of words the dimension is
> *supposed* to count, or is the score being driven by tokens that
> happen to be in the dictionary but mean something else in a
> technical-documentation register?

Method. For each dimension, the five highest-scoring libraries in the
ecosystem that the screening flagged as "high" were tokenised, and the
tokens were filtered against a hand-curated list of stems drawn from
the LIWC-22 published examples for that category. The most frequent
matching tokens are reported below, together with the share of the
LIWC score that the curated stems alone reproduce (a high share means
the dimension is well-captured by its canonical seed words; a low
share means LIWC is matching peripheral entries in its own dictionary,
which is the regime where false positives in a code-doc register are
most likely).

Script: `src/common/verify_liwc_dimensions.py`
Raw output: re-run the script to regenerate.

The verdict at the end of each row uses three labels:

- **clean**: the matched tokens have the meaning the dimension is
  named for; the score is interpretable as written.
- **mixed**: some matches are on-meaning, but a substantial fraction
  of the score comes from tokens whose code-context meaning differs
  from their LIWC meaning. Findings on this dimension should be
  qualified.
- **register-shifted**: the dominant matched tokens are in the LIWC
  dictionary but their meaning in a technical-documentation register
  is materially different from the affective/cognitive construct LIWC
  names. Findings on this dimension cannot be interpreted at face
  value.

---

## Summary table

| Dimension | Top tokens in high-scoring libraries (aggregated) | Verdict |
|---|---|---|
| `emotion`    | `like` (365), `good` (33), `nice` (19), `love` (2), `great` (2) | **register-shifted**: dominated by idiomatic *like* ("looks like", "such as") |
| `emo_neg`    | `error` (299), `errors` (82), `issues` (76), `failed` (17), `failure` (12), `wrong` (7), `bad` (6) | **mixed**: words *are* in the negative dictionary, but they describe runtime errors, not author affect |
| `emo_anger`  | curated stems matched <0.01% of tokens; in-corpus LIWC matches are likely on words like "kill (thread)", "destroy", "block", "force" | **register-shifted**: collides with code-action vocabulary |
| `emo_sad`    | `missing` (72), `losing` (19), `lose` (10), `lost` (6) | **register-shifted**: "missing argument / lost connection", not author sadness |
| `Tone`       | `please` (61), `like` (29), `successful` (24), `easy` (9), `easier` (8) | **mixed**: partially politeness markers ("please refer to..."), partially genuine positive evaluation |
| `WPS`        | structural: median ≈ 17–19 words/sentence in Java top-5, matches LIWC value to ±0.5 | **clean** (structural, not lexical) |
| `BigWords`   | structural: my count of ≥7-letter tokens reproduces LIWC value to ±0.7 pp; top tokens are `request`, `connection`, `execution`, `scheduler`, `disposable` | **clean** (structural; long words are domain terms, which *is* the construct of formality) |
| `ipron`      | `this` (3612), `that` (3604), `it` (1372), `its` (314), `such` (210), `these` (116), `itself` (105) | **clean**: exactly the LIWC ipron lexicon, in its intended sense |
| `tentat`     | `possible` (252), `may` (235), `some` (210), `might` (201), `something` (158), `depending` (124), `likely` (70), `could` (51) | **clean**: canonical hedge vocabulary, used in its hedging sense |
| `certitude`  | `never` (120), `always` (99), `actually` (45), `certain` (40), `sure` (32), `really` (12), `completely` (12) | **clean**: canonical certainty vocabulary, used in its certainty sense |
| `curiosity`  | `how` (112), `why` (15), `search` (14), `discovered` (11), `interested` (9), `discover` (7), `learn` (7) | **mixed**: `how` dominates (≈58% of all hits); idiomatic "how to X" in API docs is not curiosity framing |
| `achieve`    | `creates` (753), `create` (285), `make` (132), `created` (131), `perform` (120), `built` (117), `makes` (78), `work` (69) | **mixed**: `create/make/perform` *are* LIWC achieve words; in API docs they label factory methods, not goal pursuit |
| `risk`       | `security` (204), `securityexception` (197), `error` (169), `warning` (134), `safe` (121), `secure` (63), `avoid` (55), `warn` (30) | **mixed**: `warning/avoid/risk/safe` are legitimate risk language; `security*` are mostly the *domain* of one library (Spring Security) |
| `motion`     | `return` (147), `returns` (106), `passed` (58), `returned` (43), `run` (31), `sent` (20), `running` (11), `send` (9) | **register-shifted**: almost entirely function-return / parameter-passing language, not physical motion |
| `conflict`   | `arguments` (193), `argument` (79), `against` (10), `opposite` (4), `conflicting` (2), `broken` (2) | **register-shifted**: dominated by *function arguments*, not opposition or conflict |

---

## Dimension-by-dimension narrative

### Clean: `ipron`, `tentat`, `certitude`, `WPS`, `BigWords`

These five dimensions pass the construct-validity check cleanly.

- `ipron`: top matched tokens are exactly the LIWC ipron lexicon
  (`this`, `that`, `it`, `its`, `such`, `these`, `itself`) and the
  hand-curated stems already reproduce ≈4.9% of tokens, essentially
  the entire LIWC score (~5.3%). The Java > Python finding on `ipron`
  reflects a real preference for impersonal/abstract reference in
  Java API documentation.

- `tentat`: dominated by `may`, `might`, `possible`, `some`,
  `something`, `depending`, `likely`, `could`, every one is a
  textbook hedge. The Python > Java finding is interpretable as
  written: Python documentation hedges more.

- `certitude`: dominated by `never`, `always`, `actually`, `certain`,
  `sure`, `really`, `completely`. Every one is a textbook certainty
  marker. The Java > Python > JavaScript ordering is interpretable as
  written.

- `WPS`: the avg-words-per-sentence I compute in Python matches LIWC's
  value to ±0.5 across the top five libraries. The construct is
  literally sentence length, and Java's top-five really do average
  17–19 words/sentence. **Clean.**

- `BigWords`: my count of ≥7-letter tokens reproduces LIWC's `BigWords`
  to ±0.7 percentage points. The top long words are domain technical
  vocabulary (`scheduler`, `disposable`, `throwable`, `authentication`,
  `collection`, `annotation`). The construct LIWC names is "formal /
  Latinate vocabulary", and these words *are* exactly that, so the
  finding "Java more formal" is supported. **Clean.**

### Mixed: `emo_neg`, `Tone`, `curiosity`, `achieve`, `risk`

These are real LIWC matches but the dominant tokens have a
documentation-specific reading that pulls the construct off-centre.

- `emo_neg`: nearly the entire score is `error`, `errors`, `issues`,
  `failure`, `failed`, `wrong`. These *are* in the negative-emotion
  dictionary, but in the Python corpus they overwhelmingly refer to
  *runtime errors* (e.g. "raises a `ValueError` when..."), not to the
  author's affective stance. The Python > Java effect should be read
  as "Python documentation talks about errors / failure modes more
  often", not as "Python authors are more negatively affected".

- `Tone`: ~30% of the positive-tone matches in the top-five Java
  libraries are the word `please` ("please refer to...", "please file
  an issue"), which is a politeness marker rather than a positive
  affective evaluation. The remainder (`successful`, `easy`, `easier`,
  `like`, `nice`) is genuine. Read the finding as "Java documentation
  more polite + more positive-evaluative" rather than as a pure
  valence claim.

- `curiosity`: 58% of all curated hits across the Java top-five are
  the single token `how`. `how` *is* in the LIWC curiosity
  dictionary, but in API documentation the dominant idiom is
  "How to install / How to configure", which is a *reader-facing
  instructional* register, not the author expressing curiosity.
  Treat the J > P finding as a register marker ("Java READMEs use
  more 'how-to' framing"), not as a claim about epistemic stance.

- `achieve`: the score is dominated by `create`, `creates`, `created`,
  `make`, `makes`, `made`, `perform`, `built`, `build`, `work`. These
  are bona fide LIWC achieve words, but in API documentation they
  almost always label *factory methods* (`createConnection()`,
  `Builder.build()`). The "Java more achievement-oriented" finding
  should be read as "Java API surfaces are more factory-method
  heavy", which is itself a real and consistent stylistic
  observation about Java but is not the same construct as
  motivational goal pursuit.

- `risk`: the top-five Java libraries on this dimension are dominated
  by Spring Security and Apache Commons Lang, where `security`,
  `secure`, `securityexception`, `securerandom`, `securitycontext`
  alone account for ≈40% of the matches. Half of `risk` is therefore
  the topical *domain* of a few libraries rather than a stylistic
  ecosystem trait. The remainder (`warn`, `warning`, `avoid`, `error`,
  `safe`, `prevent`) is legitimate risk-aversion vocabulary and
  matches the LIWC construct. The J > P > JS monotonic pattern
  should be qualified: it is partly real (Java APIs use more
  defensive language) and partly a sampling artefact of including
  security libraries.

### Register-shifted: `emotion`, `emo_anger`, `emo_sad`, `motion`, `conflict`

For these dimensions, the dominant matched tokens have a
code-documentation meaning that is materially different from the
affective construct.

- `emotion`: the single token `like` accounts for 365 of the 428
  curated hits in the Python top-five (≈85%). In Python documentation
  the dominant usage of `like` is `array-like`, `dict-like`,
  `file-like`, `string-like`, `looks like`, `such as`, i.e. the
  preposition-and-simile sense, not the affective verb sense. The
  LIWC `emotion` dictionary contains `like` because it can express
  positive affect, but the construct LIWC names ("emotion-word
  usage") is not what is driving the Python > Java effect.
  **The headline "Python more emotional" finding does not survive
  this check.** What does survive is the more conservative finding
  that Python documentation uses more *evaluative* hedged
  comparison language (`like X`, `similar to X`).

- `emo_anger`: the curated anger stems hit essentially zero tokens
  in the highest-scoring Python libraries, yet the LIWC scores are
  non-zero (0.5–0.8%). The dictionary must therefore be matching
  on words outside the canonical anger lexicon, most plausibly
  code-action verbs like `kill` (thread), `destroy` (handle),
  `block` (call), `force` (flag), which appear in LIWC's broader
  anger entries. The Python > Java effect on `emo_anger` is best
  read as a co-effect of `emo_neg`: it is not independent evidence
  of anger expression.

- `emo_sad`: dominated by `missing` (72 of 118 hits), with `losing`,
  `lose`, `lost` making up most of the remainder. In the Python
  corpus these are almost entirely "missing argument", "lost
  connection", "missing key in dict", i.e. code-state terms.
  **The "Python more sad" reading is not supported by this check.**
  The conservative reading is "Python documentation describes
  failure-state vocabulary (loss/missingness) more often", which
  is the same effect as `emo_neg` re-expressed in different lexicon.

- `motion`: dominated by `return`, `returns`, `returned`, `passed`,
  `pass`, `passing`, `send`, `sent`. All of these are LIWC motion
  words by their general-English sense, but in API documentation
  they are almost without exception the *function-return* /
  *argument-passing* sense, not physical motion. The "Python more
  processual / action-oriented" reading should be replaced by the
  more accurate "Python documentation describes function call
  semantics, return values, argument passing, at a higher rate
  per word". This is still a real ecosystem difference but is not
  the affordance the dimension's name implies.

- `conflict`: dominated by `arguments`, `argument`, with a long tail
  of `against`, `opposite`, `conflicting`, `broken`. The dominant
  token here is *function arguments*, not the LIWC sense of
  conflict (argue / oppose / fight). The Python > Java finding on
  `conflict` is therefore a measurement artefact: it co-varies
  with how often Python documentation enumerates function
  signatures. **The "Python more conflict-oriented" reading is not
  supported.**

---

## Implications

1. **Five dimensions survive cleanly**: `ipron`, `tentat`,
   `certitude`, `WPS`, `BigWords`. These can be interpreted at face
   value. Together they support the **Style** and **Cognition** axes
   of the locked confirmatory list.

2. **Five dimensions are mixed but interpretable with caveats**,
   `emo_neg`, `Tone`, `curiosity`, `achieve`, `risk`. Each one's
   construct is better described by what is
   actually being counted:
   - `emo_neg` → "error/failure vocabulary"
   - `Tone` → "politeness + positive evaluation"
   - `curiosity` → "how-to instructional framing"
   - `achieve` → "factory-method / build vocabulary"
   - `risk` → "warning + defensive vocabulary (with topical
     confound from security libraries)"

3. **Five dimensions are register-shifted and should not be
   interpreted at the names LIWC gives them**, `emotion`, `emo_anger`,
   `emo_sad`, `motion`, `conflict`. They can still be reported (their
   ecosystem-level *signals* are real), but the interpretation must
   be rewritten in terms of what is actually being matched. In
   particular, the **Affect axis** as currently named in the original plan is misleading: only `emo_neg` provides a
   defensible affective reading (and even that one is more about
   error-state vocabulary than author affect).

4. **Recommendation for the original plan.** The
   confirmatory list itself does not need to change, the same 15
   dimensions remain the right set to test, but the axis
   descriptions and the language used to *report* findings on the
   Affect and Action axes should be reworded to reflect the
   technical-register reading. The Affect axis claim should be
   weakened from "Python more emotional" to "Python documentation
   uses more error/failure/loss-state vocabulary per word"; the
   Action axis claim should be weakened from "Python more processual
   / conflict-oriented" to "Python documentation describes
   function-call semantics (returns, arguments) at a higher rate
   per word". These are still genuine ecosystem differences but
   they are stylistic / topical rather than affective.
