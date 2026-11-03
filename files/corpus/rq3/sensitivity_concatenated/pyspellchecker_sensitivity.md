# pyspellchecker — prompt sensitivity comparison

---

## ACTUAL (human README) (699 words, capped at 300)

pyspellchecker

Pure Python Spell Checking based on
Peter
Norvig's
 blog post on setting
up a simple spell checking algorithm.

It uses a
Levenshtein Distance

algorithm to find permutations within an edit distance of 2 from the
original word. It then compares all permutations (insertions, deletions,
replacements, and transpositions) to known words in a word frequency
list. Those words that are found more often in the frequency list are

more likely
 the correct results.

pyspellchecker
 supports multiple languages including English, Spanish,
German, French, Portuguese, Arabic and Basque. For information on how the dictionaries were
created and how they can be updated and improved, please see the

Dictionary Creation and Updating
 section of the readme!

pyspellchecker
 supports
Python 3

pyspellchecker
 allows for the setting of the Levenshtein Distance (up to two) to check.
For longer words, it is highly recommended to use a distance of 1 and not the
default 2. See the quickstart to find how one can change the distance parameter.

Installation

The easiest method to install is using pip:

To build from source:

For
python 2.7
 support, install
release 0.5.6

but note that no future updates will support
python 2
.

Quickstart

After installation, using
pyspellchecker
 should be fairly straight
forward:

If the Word Frequency list is not to your liking, you can add additional
text to generate a more appropriate list for your use case.

If the words that you wish to check are long, it is recommended to reduce the

distance
 to 1. This can be accomplished either when initializing the spell
check class or after the fact.

Non-English Dictionaries

pyspellchecker
 supports several default dictionaries as part of the default
package. Each is simple to use when initializing the dictionary:

The currently supported dictionaries are:

English       - 'en'

Spanish       - 'es'

French        - 'fr'

Portuguese    - 'pt'


[... truncated at 300 words, 699 total]

---

## V0_baseline (sonnet) (903 words, capped at 300)

# pyspellchecker

`pyspellchecker` is a pure-Python spell checking library that uses word
frequency statistics to detect misspelled words and suggest corrections. It
implements a Levenshtein-distance based algorithm (similar in spirit to Peter
Norvig's classic spell-correction approach) and ships with pre-built
dictionaries for a number of languages.

## Features

- Detect unknown/misspelled words in text
- Suggest the most likely correction for a misspelled word
- Retrieve the full set of candidate corrections, not just the best guess
- Work with edit distances of 1 or 2
- Load and manage your own word frequency dictionaries (from JSON, plain
  text, lists of words, or programmatically)
- Export a word frequency dictionary for reuse or sharing
- Supports multiple languages out of the box, and is easily extended with
  custom vocabularies (e.g. domain-specific terms, product names, jargon)

## Installation

```bash
pip install pyspellchecker
```

## Core Concepts

### `SpellChecker`

`SpellChecker` is the main entry point of the library. It wraps a
`WordFrequency` instance and provides the high-level spell checking API:
finding unknown words, generating correction candidates, and returning the
single best correction.

Key methods:

- `known(words)` – filter an iterable of words down to those found in the
  dictionary.
- `unknown(words)` – filter an iterable of words down to those *not* found in
  the dictionary (i.e. likely misspelled).
- `correction(word)` – return the most probable correct spelling for a word.
- `candidates(word)` – return the full set of possible corrections for a
  word.
- `edit_distance_1(word)` / `edit_distance_2(word)` – low-level helpers that
  generate all strings within edit distance 1 or 2 of a word.
- `split_words(text)` – tokenize a string of text into words the same way the
  checker does internally.
- `word_usage_frequency(word, total_words=None)` – get the relative frequency
  of a word in the loaded corpus.
- `distance` (property) – get or set

[... truncated at 300 words, 903 total]

---

## V0_baseline (openai) (1197 words, capped at 300)

# pyspellchecker

`pyspellchecker` is a Python library for working with spelling dictionaries and word-frequency data. It provides tools to:

- Check whether words are known or unknown.
- Generate spelling candidates and corrections.
- Calculate word usage frequencies.
- Load, modify, and export frequency dictionaries.
- Tokenize text and build custom dictionaries from text files or iterables.
- Build and clean language dictionary data through helper scripts.

## Core concepts

The library centers on two classes:

- **`SpellChecker`** — provides spelling-oriented operations such as finding unknown words, generating edit-distance candidates, and selecting a correction.
- **`WordFrequency`** — stores a mapping of words to frequency counts and provides loading, mutation, tokenization, and inspection utilities.

A `SpellChecker` exposes a `WordFrequency` instance through its `word_frequency` interface. Frequency data is used when selecting likely corrections and when calculating word usage frequency.

## Installation

```bash
pip install pyspellchecker
```

## Quick start

```python
from spellchecker import SpellChecker

spell = SpellChecker()

words = ["this", "is", "a", "simple", "speling", "example"]

print(spell.unknown(words))
# {"speling"}

print(spell.correction("speling"))
# "spelling" (depending on the loaded dictionary)

print(spell.candidates("speling"))
# A set of possible dictionary words
```

## `SpellChecker`

`SpellChecker` provides the main spelling-checking interface.

### Available languages

Use `languages()` to inspect the language dictionaries available to the library:

```python
from spellchecker import SpellChecker

for language in SpellChecker.languages():
    print(language)
```

### Check known and unknown words

Pass an iterable of words to `known()` or `unknown()`:

```python
from spellchecker import SpellChecker

spell = SpellChecker()

words = ["python", "dictionary", "teh", "spellchecker"]

known_words = spell.known(words)
unknown_words = spell.unknown(words)

print(known_words)
print(unknown_words)
```

`known()` returns words found in the active dictionary. `unknown()` returns words that are not found.

### Find a correction

Use `correction()` to request the most likely correction for a word:

```python
from spellchecker import SpellChecker

spell = SpellChecker()

word = "recieve"
suggestion = spell.correction(word)

if suggestion

[... truncated at 300 words, 1197 total]

---

## V1_anon_name (sonnet) (780 words, capped at 300)

# sample-project

A lightweight, pure-Python spell checking library based on word frequency lists and Levenshtein edit distance. `sample-project` ships with prebuilt dictionaries for multiple languages and exposes a simple API for checking, correcting, and tokenizing text, as well as building and maintaining your own custom dictionaries.

## Features

- Spell checking and correction using edit-distance-based candidate generation
- Frequency-weighted suggestions (more common words are preferred corrections)
- Support for multiple bundled languages
- Fully customizable word frequency dictionaries — add, remove, or import your own word lists
- Tools for tokenizing raw text into words
- Utilities to build and clean dictionaries from raw corpora (see `scripts/build_dictionary.py`)
- Export/import dictionaries as gzipped or plain-text JSON files

## Installation

```bash
pip install sample-project
```

## Core Concepts

### `SpellChecker`

The main entry point of the library. A `SpellChecker` instance wraps a `WordFrequency` object and provides high-level operations:

- `correction(word)` — return the single best correction for a word
- `candidates(word)` — return the set of possible corrections
- `known(words)` / `unknown(words)` — filter an iterable of words into those known/unknown to the dictionary
- `edit_distance_1(word)` / `edit_distance_2(word)` — generate words within 1 or 2 edits of the input
- `split_words(text)` — tokenize a string into words using the checker's tokenizer
- `word_usage_frequency(word, total_words=None)` — get the relative frequency of a word
- `distance` — property controlling the maximum edit distance used for corrections (get/set)
- `word_frequency` — property exposing the underlying `WordFrequency` instance
- `export(filepath, encoding='utf-8', gzipped=True)` — persist the current dictionary to disk
- `SpellChecker.languages()` — classmethod listing available bundled languages

### `WordFrequency`

Manages the underlying word → frequency counts that power spell checking. Typically accessed through `SpellChecker.word_frequency`, but can also be used standalone for corpus analysis.

Key operations:

- **Loading data**: `load_dictionary(filename)`, `load_json(data)`, `load_text_file(filename)`, `load_text(text)`, `load_words(words)`
- **Editing**: `add(word,

[... truncated at 300 words, 780 total]

---

## V1_anon_name (openai) (1116 words, capped at 300)

# sample-project

A Python library for dictionary-backed spell checking and word-frequency management.

`sample-project` provides:

- A `SpellChecker` for identifying unknown words, generating correction candidates, and selecting likely corrections.
- A `WordFrequency` store for loading, updating, filtering, and inspecting word-frequency dictionaries.
- Import/export helpers for dictionary data.
- Build scripts for creating and cleaning language-specific word-frequency dictionaries.

## Installation

```bash
pip install sample-project
```

## Quick start

```python
from spellchecker.spellchecker import SpellChecker

spell = SpellChecker()

word = "speling"

print(spell.correction(word))
# Example result: "spelling"

print(spell.candidates(word))
# Example result: {"spelling", ...}
```

Check a collection of words:

```python
from spellchecker.spellchecker import SpellChecker

spell = SpellChecker()

words = ["this", "is", "a", "speling", "test"]

print(spell.known(words))
# {"this", "is", "a", "test"}

print(spell.unknown(words))
# {"speling"}
```

## Core concepts

### `SpellChecker`

`SpellChecker` is the primary interface for spell-checking text and words. It uses an associated `WordFrequency` dictionary to determine whether words are known and to rank possible corrections.

Key capabilities include:

- Listing available languages with `SpellChecker.languages()`.
- Splitting text into words with `split_words()`.
- Identifying known and unknown words.
- Generating edit-distance candidates.
- Returning the most likely correction for a misspelled word.
- Calculating word-usage frequency.
- Exporting the current dictionary.

### `WordFrequency`

`WordFrequency` manages the dictionary used by a spell checker. It stores words and their occurrence counts, along with derived dictionary metadata such as:

- Total word count
- Number of unique words
- Available letters
- Length of the longest word

A `WordFrequency` object can load dictionary files, JSON-compatible mappings, plain text, and arbitrary word iterables. It also supports adding and removing words and filtering low-frequency entries.

## Using a language dictionary

Inspect the language dictionaries supported by the installed package:

```python
from spellchecker.spellchecker import SpellChecker

for language in SpellChecker.languages():
    print(language)
```

Create a spell checker using the language configuration supported by

[... truncated at 300 words, 1116 total]

---

## V2_length_cap (sonnet) (451 words, capped at 300)

# pyspellchecker

`pyspellchecker` is a pure-Python library for spelling correction and word-frequency-based text analysis. It uses word frequency lists and Levenshtein edit distance to identify misspelled words, suggest corrections, and provide statistics about word usage in a corpus. It ships with built-in dictionaries for several languages and supports loading custom dictionaries or text corpora.

## Installation

```bash
pip install pyspellchecker
```

## Core Concepts

### `SpellChecker`

The main entry point for spell-checking. A `SpellChecker` instance wraps a `WordFrequency` object and provides methods to check words against it, find likely corrections, and generate candidate spellings using edit distance.

Key methods:

- `known(words)` / `unknown(words)` — filter an iterable of words into those present or absent from the dictionary.
- `correction(word)` — return the most likely correct spelling for a word.
- `candidates(word)` — return the full set of plausible correction candidates.
- `edit_distance_1(word)` / `edit_distance_2(word)` — generate words one or two edits away from the input.
- `split_words(text)` — tokenize a string into words.
- `word_usage_frequency(word)` — return the relative frequency of a word in the dictionary corpus.
- `distance` (property) — the maximum edit distance considered when generating candidates (typically 1 or 2).
- `export(filepath)` — save the current word frequency dictionary to disk.
- `languages()` (classmethod) — list built-in language dictionaries available.

### `WordFrequency`

Manages the underlying word/frequency data used by `SpellChecker`. Accessible via `SpellChecker.word_frequency`.

Key methods:

- `load_dictionary(filename)` / `load_json(data)` — load a prebuilt frequency dictionary.
- `load_text_file(filename)` / `load_text(text)` — build frequency data from raw text, with optional custom tokenizer.
- `load_words(words)` / `add(word)` — manually add words/counts.
- `remove(word)` / `remove_words(words)` / `remove_by_threshold(threshold)` — prune the dictionary.
- `keys()` / `words()` / `items()` / `dictionary` — inspect the loaded data.
- `total_words`, `unique_words`, `letters`, `longest_word_length` — corpus statistics.

## Usage Examples

### Basic spell checking

```python

[... truncated at 300 words, 451 total]

---

## V2_length_cap (openai) (528 words, capped at 300)

# pyspellchecker

`pyspellchecker` is a Python library for identifying unknown words, generating spelling candidates, selecting likely corrections, and maintaining word-frequency dictionaries.

It includes built-in language support exposed through `SpellChecker.languages()`, configurable edit-distance matching, and tools for loading, extending, trimming, and exporting frequency dictionaries.

## Installation

```bash
pip install pyspellchecker
```

## Quick start

Create a spell checker, find misspellings, and request corrections:

```python
from spellchecker import SpellChecker

spell = SpellChecker()

words = ["spelling", "pythn", "library", "recieve"]

misspelled = spell.unknown(words)
print(misspelled)
# {"pythn", "recieve"}

for word in misspelled:
    print(word, "->", spell.correction(word))
# pythn -> python
# recieve -> receive
```

Use `known()` when you only need the words recognized by the current dictionary:

```python
recognized = spell.known(["python", "pythn", "dictionary"])
```

## `SpellChecker`

`SpellChecker` is the primary interface for spell-checking operations. It owns a `WordFrequency` dictionary and uses that data to determine whether words are known and which candidate correction is most likely.

### Language support

List supported dictionary languages:

```python
from spellchecker import SpellChecker

print(list(SpellChecker.languages()))
```

A checker can be configured with an available language when it is created:

```python
spell = SpellChecker(language="en")
```

### Checking text

`split_words()` splits text into individual words suitable for checking:

```python
text = "Ths is a smple sentence."
words = spell.split_words(text)

print(spell.unknown(words))
```

For a single word:

- `correction(word)` returns the most likely spelling correction, or `None`.
- `candidates(word)` returns possible corrections, or `None` when no candidates are available.

```python
word = "teh"

print(spell.candidates(word))
print(spell.correction(word))
```

### Edit distance

The `distance` property controls the maximum edit distance used while finding candidates.

```python
spell.distance = 1
nearby = spell.edit_distance_1("speling")

spell.distance = 2
more_nearby = spell.edit_distance_2("speling")
```

`edit_distance_1()` returns words one edit away. `edit_distance_2()` returns words up to the second edit-distance expansion.

### Word usage frequency

Dictionary frequencies can be used to inspect a word's relative usage:

```python

[... truncated at 300 words, 528 total]

---

## V3_paraphrase (sonnet) (1130 words, capped at 300)

# pyspellchecker

A pure Python spell-checking library that uses word frequency data to detect misspellings and suggest corrections. Rather than relying on a fixed dictionary lookup, `pyspellchecker` uses Levenshtein distance (edit distance) combined with word frequency statistics to determine the most probable correction for a given word — similar in spirit to Peter Norvig's classic spelling correction algorithm.

The library ships with pre-built frequency dictionaries for multiple languages and also includes the tooling used to build those dictionaries from raw corpora, so you can extend or replace the built-in language data with your own.

## Features

- Spelling correction based on edit distance (1 or 2) and word usage frequency
- Support for multiple languages out of the box
- Ability to load your own word frequency dictionaries, JSON data, or plain text corpora
- Fine-grained control over the frequency dictionary (add/remove words, set thresholds, export/import)
- Tokenization utilities for splitting arbitrary text into words
- Scripts for building and cleaning custom dictionaries from source text

## Installation

```bash
pip install pyspellchecker
```

## Quick Start

```python
from spellchecker import SpellChecker

spell = SpellChecker()  # loads default word frequency list (English by default)

# find those words that may be misspelled
misspelled = spell.unknown(["something", "is", "hapenning", "here"])

for word in misspelled:
    # get the one `most likely` correction
    print(spell.correction(word))

    # get a list of `likely` options
    print(spell.candidates(word))
```

## Core Concepts

### `SpellChecker`

The main entry point for spell checking. A `SpellChecker` instance wraps a `WordFrequency` object (accessible via `spell.word_frequency`) that holds the underlying word counts used to judge correctness and likelihood.

Key methods:

- **`known(words)`** — given an iterable of words, returns the subset that exist in the frequency dictionary.
- **`unknown(words)`** — the inverse of `known`; returns words that are *not* recognized, i.e. likely misspellings.
- **`candidates(word)`** —

[... truncated at 300 words, 1130 total]

---

## V3_paraphrase (openai) (1303 words, capped at 300)

# pyspellchecker

`pyspellchecker` provides dictionary-backed spelling utilities for Python. It can tokenize text, identify known and unknown words, generate edit-distance candidates, select a likely correction, and maintain word-frequency dictionaries that influence correction choices.

The package is organized around two main classes:

- `SpellChecker` — checks words and proposes corrections using a word-frequency dictionary.
- `WordFrequency` — stores, loads, updates, and exports word counts used by the spell checker.

It also includes utility functions for file handling and decorators, plus dictionary-building helpers used to prepare language dictionaries.

## Installation

Install the package with your preferred Python package workflow:

```bash
pip install pyspellchecker
```

## Quick start

```python
from spellchecker.spellchecker import SpellChecker

spell = SpellChecker()

word = "speling"

if word in spell.unknown([word]):
    print(f"Unknown word: {word}")

    suggestion = spell.correction(word)
    if suggestion is not None:
        print(f"Suggested correction: {suggestion}")

    alternatives = spell.candidates(word)
    if alternatives:
        print("Candidates:", sorted(alternatives))
```

Typical output may look like:

```text
Unknown word: speling
Suggested correction: spelling
Candidates: ['spieling', 'spelling', ...]
```

## `SpellChecker`

`SpellChecker` is the high-level interface for checking text and obtaining spelling suggestions.

```python
from spellchecker.spellchecker import SpellChecker

spell = SpellChecker()
```

### Available languages

Use `languages()` to inspect the language dictionaries available to the installation:

```python
for language in SpellChecker.languages():
    print(language)
```

`languages()` returns an iterable of language identifiers.

### Split text into words

Use `split_words()` to obtain the words recognized in a piece of text:

```python
text = "This sentence contains a misspeled word."
words = list(spell.split_words(text))

print(words)
```

This is useful when checking an entire document rather than individual words.

### Find known and unknown words

`known()` returns words found in the current dictionary. `unknown()` returns words that are not found.

```python
words = ["correct", "speling", "dictionary"]

known_words = spell.known(words)
unknown_words = spell.unknown(words)

print("Known:", known_words)
print("Unknown:", unknown_words)
```

Example:

```python
if spell.unknown(["recieve"]):
print("The word is not present

[... truncated at 300 words, 1303 total]
