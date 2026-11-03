# xsdata — prompt sensitivity comparison

---

## ACTUAL (human README) (277 words, capped at 300)

Naive XML Bindings for python

xsData is a complete data binding library for python allowing developers to access and
use XML and JSON documents as simple objects rather than using DOM.

The code generator supports XML schemas, DTD, WSDL definitions, XML & JSON documents. It
produces simple dataclasses with type hints and simple binding metadata.

The included XML and JSON parser/serializer are highly optimized and adaptable, with
multiple handlers and configuration properties.

xsData is constantly tested against the

W3C XML Schema 1.1 test suite
.

Getting started

Check the
documentation
 for more ✨✨✨

Features

Code Generator

XML Schemas 1.0 & 1.1

WSDL 1.1 definitions with SOAP 1.1 bindings

DTD external definitions

Directly from XML and JSON Documents

Extensive configuration to customize output

Pluggable code writer for custom output formats

Default Output

Pure python dataclasses with metadata

Type hints with support for forward references and unions

Enumerations and inner classes

Support namespace qualified elements and attributes

Data Binding

XML and JSON parser, serializer

PyCode serializer

Handlers and Writers based on lxml and native xml python

Support wildcard elements and attributes

Support xinclude statements and unknown properties

Customize behaviour through config

Changelog: 24.6.1 (2024-06-28)

Fixes

Ruff check command typo breaks generator with v0.5.0
  (
#1061
)

Changelog: 24.6 (2024-06-24)

Features

Add class and field info in parsing warnings
  (
#1036
)

Remove whitespace from bytes encoded xml strings
  (
#1037
)

Improve codegen performance (
#1043
)

Fixes

JSON serializer fails on derived elements
  (
#1053
)

Update typing-extensions minimum version
  (
#1039
)

Avoid using not-threadsafe warnings.catch_warning
  (
#1042
)

Unnest classes doesn't update inner classes recursively
  (
#1047
)

Restore support for optional lists
  (
#1053
)

---

## V0_baseline (sonnet) (1089 words, capped at 300)

# xsdata

**xsdata** is a Python library and command-line tool for working with XML and JSON data using Python dataclasses. It generates strongly-typed Python dataclasses from XML Schemas (XSD), DTDs, WSDL definitions, or even existing XML/JSON documents, and it provides high-performance parsers and serializers to bind data between those dataclasses and XML/JSON.

## Features

- **Code generation** from XSD schemas, DTDs, WSDL service definitions, and sample XML/JSON documents into Python dataclasses.
- **XML binding** — parse XML documents directly into dataclass instances, and serialize dataclass instances back to XML.
- **JSON binding** — parse and serialize dataclass instances to/from JSON.
- **SOAP/WSDL client** support for calling web services described by WSDL.
- **Pluggable architecture** — custom type converters, class type backends (e.g., dataclasses vs. attrs), and custom code generators can be registered.
- **CLI** (`xsdata generate`, `xsdata download`, `xsdata init-config`) for driving code generation from the command line.

## Installation

```bash
pip install xsdata[cli,lxml,soap]
```

## Command-line usage

Generate Python dataclasses from an XSD schema:

```bash
xsdata generate schema.xsd --package myapp.models
```

Generate from a directory of schemas recursively:

```bash
xsdata generate ./schemas --package myapp.models --recursive
```

Download a schema and all of its includes/imports to a local directory:

```bash
xsdata download http://example.com/schema.xsd --output ./schemas
```

Create a reusable configuration file (`.xsdata.xml`) to store generator preferences:

```bash
xsdata init-config
```

The CLI is implemented on top of `click` (see `xsdata/cli.py`), and all generation options map to fields on `GeneratorConfig` (see below).

## Core concepts

### Code generation pipeline

The code generation flow (driven by `ResourceTransformer` in `xsdata/codegen/transformer.py`) works roughly like this:

1. **Parsing** — Source files (XSD, DTD, WSDL, XML, JSON) are parsed into intermediate models:
   - `SchemaParser` / `xsdata.models.xsd.Schema` for XSD
   - `DtdParser` / `xsdata.models.dtd.Dtd` for DTDs
   - `DefinitionsParser` / `xsdata.models.wsdl.Definitions` for WSDL
- `ElementMapper` / `DictMapper` for raw

[... truncated at 300 words, 1089 total]

---

## V0_baseline (openai) (2119 words, capped at 300)

# xsdata

`xsdata` is a Python data-binding and code-generation library for XML-centric formats. It provides tools to:

- Generate Python models from **XML Schema (XSD)**, **WSDL**, **DTD**, XML documents, and JSON documents.
- Parse XML, JSON, and dictionary data into Python dataclass models.
- Serialize dataclass models back to XML, JSON, dictionaries, Python code, or XML trees.
- Work with XML namespaces, schema datatypes, wildcard content, substitution groups, derived elements, and SOAP/WSDL-style services.
- Customize generated package layout, naming conventions, output format, substitutions, and extensions.

The library is organized around two complementary workflows:

1. **Code generation**: transform schema-like resources into an intermediate class model and render Python source files.
2. **Runtime binding**: parse and serialize Python dataclasses using XML metadata.

---

## Features

- XML Schema, WSDL, DTD, XML, JSON, and dictionary input support
- Python dataclass-based XML binding
- XML and JSON parsers and serializers
- XML namespace and QName handling
- XML Schema-compatible date, time, duration, period, base64, and hex-binary values
- Wildcard XML content through `AnyElement`
- Polymorphic and derived XML values through `DerivedElement`
- Configurable Python code generation
- Dependency resolution and import generation for generated modules
- SOAP-oriented client and transport abstractions
- Extensible converter registry and generator registration

---

## Runtime XML Binding

The runtime API lives primarily under `xsdata.formats.dataclass`.

A Python dataclass becomes an XML binding model by declaring XML metadata on fields. `XmlParser` reads XML into those models, and `XmlSerializer` writes models back to XML.

### Define a model

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Book:
    class Meta:
        name = "book"
        namespace = "urn:example:library"

    isbn: Optional[str] = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    title: Optional[str] = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "urn:example:library",
            "required": True,
        },
    )
    author: Optional[str] = field(
        default=None,
        metadata={
            "type": "Element",

[... truncated at 300 words, 2119 total]

---

## V1_anon_name (sonnet) (699 words, capped at 300)

# xsdata

**xsdata** is a Python library and command-line tool for working with XML, JSON, and related schema-based data formats. It generates Python dataclasses from XML Schema (XSD), WSDL, DTD, and even raw XML/JSON documents, and provides a full-featured binding layer for serializing and parsing data to and from these generated models.

## Features

- **Code generation** from:
  - XML Schema (`.xsd`) definitions
  - WSDL (`Definitions`) service descriptions
  - DTD documents
  - Raw XML/JSON documents (schema inference)
- **Dataclass-based data binding**: parse XML/JSON into typed Python dataclasses and serialize them back
- **Flexible XML parsing** using either `lxml` or the standard library's `xml.sax`/`xml.etree`
- A **command-line interface** (`xsdata`) for generating code and downloading remote schemas
- Rich **type conversion** support for XML Schema datatypes (dates, durations, QNames, binary types, etc.)
- A pluggable **code generation pipeline** built from composable "handlers" that transform an intermediate class model

## Installation

```bash
pip install xsdata[lxml,soap]
```

## Command-Line Usage

Generate Python dataclasses from a schema:

```bash
xsdata generate schema.xsd --package myapp.models
```

Download a schema and all its includes/imports:

```bash
xsdata download http://example.com/schema.xsd --output ./schemas
```

Initialize a project configuration file (`.xsdata.xml`):

```bash
xsdata init-config
```

## Architecture Overview

xsdata's codegen pipeline works in three broad stages:

1. **Parsing** — Source documents (XSD, WSDL, DTD, XML, JSON) are parsed into structured object models:
   - `xsdata.models.xsd.Schema` for XML Schema
   - `xsdata.models.wsdl.Definitions` for WSDL
   - `xsdata.models.dtd.Dtd` for DTDs

2. **Mapping** — "Mapper" classes convert these parsed models into a common intermediate representation, `xsdata.codegen.models.Class` (with `Attr`, `AttrType`, `Extension`, etc.):
   - `SchemaMapper` — XSD → `Class`
   - `DefinitionsMapper` — WSDL → `Class`
   - `DtdMapper` — DTD → `Class`
   - `ElementMapper` / `DictMapper` — infer `Class` models directly from XML/JSON documents

3. **Processing & Generation** — The `ClassContainer` runs an ordered pipeline of `HandlerInterface` implementations (in `xsdata.codegen.handlers`) that

[... truncated at 300 words, 699 total]

---

## V1_anon_name (openai) (1878 words, capped at 300)

# sample-project

`sample-project` is a Python toolkit for working with XML-oriented data models. Its API provides:

- **XML, JSON, dictionary, and Python-code serialization**
- **Parsing XML and JSON into Python dataclasses**
- **XML Schema (XSD), WSDL, and DTD parsing**
- **Schema/document-to-dataclass code generation**
- **XML datatype conversion and namespace utilities**
- **SOAP-style service client and transport support**
- **Tools for inspecting, transforming, validating, and generating model classes**

The public modules are exposed under the `xsdata` package namespace.

## Features

### Runtime data binding

Use dataclasses with XML metadata to parse and serialize structured XML documents:

- `XmlParser` parses XML into typed dataclasses.
- `XmlSerializer` serializes dataclass instances to XML.
- `JsonParser` and `JsonSerializer` handle JSON.
- `DictDecoder` and `DictEncoder` bind models to and from dictionaries.
- `TreeParser` and `TreeSerializer` work with XML element trees.
- `PycodeSerializer` renders Python code that recreates an object.

### Schema-driven code generation

The code-generation subsystem can process XML Schema, WSDL, DTD, XML, JSON, and dictionary-like source documents:

- `ResourceTransformer` coordinates resource loading, parsing, mapping, analysis, and generation.
- `SchemaParser`, `DefinitionsParser`, and `DtdParser` parse XSD, WSDL, and DTD inputs.
- `SchemaMapper`, `DefinitionsMapper`, `DtdMapper`, `ElementMapper`, and `DictMapper` convert parsed documents into code-generation `Class` models.
- `ClassContainer`, `ClassValidator`, and code-generation handlers normalize, validate, and transform generated models.
- `DataclassGenerator` renders Python dataclasses.
- `CodeWriter` writes generated results using a configured generator.

### XML metadata and generic values

The runtime metadata layer represents how Python fields map to XML:

- `XmlContext` caches and resolves metadata for binding models.
- `XmlMetaBuilder` and `XmlVarBuilder` inspect model types and build XML metadata.
- `XmlMeta` represents a class-level XML binding.
- `XmlVar` represents an XML-bound field.
- `AnyElement` represents arbitrary XML content.
- `DerivedElement[T]` represents an element whose runtime value has a derived type.

### XML datatypes and conversion

The converter framework maps

[... truncated at 300 words, 1878 total]

---

## V2_length_cap (sonnet) (419 words, capped at 300)

# xsdata

**xsdata** is a Python library and code generator for working with XML, JSON, WSDL, and XML Schema (XSD) / DTD definitions. It can generate Python dataclasses from XSD/DTD/WSDL sources, and it provides a full runtime for serializing and parsing XML and JSON documents to and from those dataclasses.

## What it does

xsdata is split into two complementary halves:

1. **Code generation (`xsdata.codegen`)** — parses XML Schema, DTD, or WSDL definitions and transforms them into an internal model (`Class`, `Attr`, `AttrType`, `Extension`) through a pipeline of *handlers* orchestrated by `ClassContainer`. The result is rendered into Python dataclasses (or other formats) by a pluggable `AbstractGenerator`, with `DataclassGenerator` as the default implementation using Jinja2 templates and `Filters` for code formatting.
2. **Runtime (`xsdata.formats.dataclass`)** — parses and serializes XML/JSON data into/out of plain Python dataclasses, using `XmlContext` to introspect dataclass metadata (`XmlMeta`, `XmlVar`) built via `XmlMetaBuilder`.

## Key components

- **`xsdata.cli`** — the `xsdata` command line tool (`generate`, `download`, `init-config`) drives schema-to-code generation from the shell.
- **`ResourceTransformer`** — orchestrates downloading/parsing schema, DTD, and WSDL sources and converting them into `Class` objects.
- **`ClassContainer` / handlers** — a pipeline of transformation steps (flattening extensions, resolving references, disambiguating choices, renaming duplicates, etc.) that normalize the raw parsed classes into clean, generateable models.
- **`DependenciesResolver`** — computes imports and generation order between classes.
- **`CodeWriter` / `DataclassGenerator`** — renders final Python source files from `Class` definitions, using `GeneratorConfig` for style/output preferences.
- **`XmlContext`, `XmlParser` family (`NodeParser`, `XmlParser`, `TreeParser`), `JsonParser`** — parse XML/JSON into dataclass instances.
- **`XmlSerializer`, `JsonSerializer`, `PycodeSerializer`** — serialize dataclass instances back into XML, JSON, or Python source code.
- **`Client`** — a simple SOAP/WSDL-based client built on `Config` and `Transport`.
- **`Converter` / `ConverterFactory`** — pluggable type conversion between Python types and XML Schema datatypes (dates, decimals, QNames, enums, etc.).


[... truncated at 300 words, 419 total]

---

## V2_length_cap (openai) (539 words, capped at 300)

# xsdata

**xsdata** is a Python toolkit for working with XML-centric data models. It provides tools to:

- Generate Python dataclasses from XML Schema (XSD), WSDL, DTD, XML, and JSON resources
- Parse XML and JSON documents into typed dataclass instances
- Serialize dataclass instances to XML, JSON, Python code, or an XML tree
- Convert XML-compatible primitive values such as dates, durations, QNames, decimals, and enums
- Build SOAP-style client payloads and transport requests
- Customize naming, output structure, code generation, and serialization behavior

The library is organized around two complementary workflows: **code generation** and **runtime binding**.

## Installation

```bash
pip install xsdata
```

## Code generation

The command-line interface exposes configuration, downloading, and generation operations:

```bash
xsdata init-config
xsdata generate path/to/schema.xsd
```

Resources can also be processed programmatically with `ResourceTransformer`. It accepts a collection of resource URIs and classifies and transforms supported input types, including schemas, WSDL definitions, DTDs, XML documents, and JSON documents.

```python
from xsdata.codegen.transformer import ResourceTransformer

transformer = ResourceTransformer()
transformer.process([
    "schemas/customer.xsd",
    "schemas/orders.xsd",
])
```

The generation pipeline maps source documents into internal `Class`, `Attr`, `AttrType`, `Extension`, and `Restrictions` models. A `ClassContainer` coordinates normalization and validation passes, while handlers process details such as extensions, attribute groups, duplicate names, choice fields, circular references, wrappers, and inner classes.

`CodeWriter` renders processed classes using a registered generator. The built-in `DataclassGenerator` produces Python dataclass modules.

```python
from xsdata.codegen.writer import CodeWriter
from xsdata.models.config import GeneratorConfig

config = GeneratorConfig.create()
writer = CodeWriter.from_config(config)

# `classes` is a list of processed xsdata.codegen.models.Class objects.
writer.write(classes)
```

## XML dataclass binding

Generated models are ordinary Python dataclasses with XML metadata. At runtime, `XmlParser` reads XML into those models, and `XmlSerializer` writes them back to XML.

```python
from dataclasses import dataclass, field
from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.serializers import XmlSerializer


@dataclass
class Customer:
id: int = field(metadata={"type":

[... truncated at 300 words, 539 total]

---

## V3_paraphrase (sonnet) (1366 words, capped at 300)

# xsdata

**xsdata** is a Python library and command-line tool for working with XML and JSON data models. It generates Python dataclasses from XML Schema (XSD), DTD, WSDL, and sample XML/JSON documents, and provides a full-featured binding engine to serialize and deserialize data between those dataclasses and XML or JSON.

At its core, xsdata solves two related problems:

1. **Code generation** — turning schema definitions (XSD, DTD, WSDL) or raw documents (XML, JSON) into idiomatic, type-annotated Python dataclasses.
2. **Data binding** — parsing XML/JSON into instances of those dataclasses, and serializing dataclass instances back into XML/JSON, with full support for namespaces, mixed content, wildcards, choices, and more.

It ships as both an importable Python API and a `xsdata` CLI command.

---

## Installation

```bash
pip install xsdata[cli,lxml]
```

The `cli` extra pulls in the click-based command line interface; `lxml` enables the faster lxml-based XML handlers.

---

## Command Line Usage

The CLI is the most common entry point for code generation.

```bash
# Generate dataclasses from a schema
xsdata generate schema.xsd --package my_models

# Generate from a WSDL, XML, JSON or DTD source
xsdata generate service.wsdl --package my_client
xsdata generate sample.xml --package my_models

# Create a reusable generator config file (.xsdata.xml)
xsdata init-config

# Download a schema and all of its imported/included resources locally
xsdata download http://example.com/schema.xsd ./local-schemas
```

Configuration for generation (structure style, docstring style, naming conventions, aliases, extensions, etc.) is controlled by `GeneratorConfig`, which can be created programmatically or read from/written to an `.xsdata.xml` config file via `GeneratorConfig.create()`, `GeneratorConfig.read(path)`, and `GeneratorConfig.write(out, config)`.

---

## Code Generation Pipeline

Code generation is organized as a pipeline: **parse → map → validate/transform → resolve → write**.

### 1. Transformation entry point

`xsdata.codegen.transformer.ResourceTransformer` is the top-level orchestrator. Given a list of URIs (schema, WSDL, DTD, XML, or JSON sources), it:

- classifies

[... truncated at 300 words, 1366 total]

---

## V3_paraphrase (openai) (2120 words, capped at 300)

# xsdata

**xsdata** is a Python toolkit for working with XML-oriented data models. It provides:

- Code generation from XML Schema (XSD), WSDL, DTD, XML, JSON, and dictionary-like documents.
- Python dataclass generation with XML metadata.
- XML, JSON, dictionary, and Python-code serialization.
- XML, JSON, dictionary, and tree-based parsing.
- XML Schema/WSDL model objects and conversion utilities.
- Type conversion support for XML-compatible primitive and temporal types.
- SOAP-style client support for generated service models.

The project is designed around Python dataclasses: generate or define a dataclass model, then use the parsing and serialization APIs to move between Python objects and XML/JSON documents.

## Installation

```bash
pip install xsdata
```

Depending on the XML backend in use, optional dependencies such as `lxml` may also be useful.

## Quick start

Define an XML-aware dataclass using standard `dataclasses` fields and field metadata:

```python
from dataclasses import dataclass, field

from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.serializers import XmlSerializer


@dataclass
class Book:
    class Meta:
        name = "book"

    title: str = field(
        metadata={
            "type": "Element",
        }
    )
    isbn: str = field(
        metadata={
            "type": "Attribute",
        }
    )


xml = """\
<book isbn="978-0-00-000000-0">
  <title>Example Book</title>
</book>
"""

parser = XmlParser()
book = parser.from_string(xml, Book)

assert book.title == "Example Book"
assert book.isbn == "978-0-00-000000-0"

serializer = XmlSerializer()
result = serializer.render(book)

print(result)
```

The serializer produces XML using the model’s class and field metadata.

## Generating models

The command-line interface includes commands for initializing configuration, downloading resources, and generating code.

A typical generation workflow is:

```bash
xsdata generate schema.xsd --package generated.models
```

The generator accepts resource inputs that are processed by `ResourceTransformer`. Its public interface indicates support for several input categories:

| Source type | Processing path |
| --- | --- |
| XML Schema | Schema parser and `SchemaMapper` |
| WSDL definitions | Definitions parser and

[... truncated at 300 words, 2120 total]
