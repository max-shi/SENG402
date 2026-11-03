# web-fragments — prompt sensitivity comparison

---

## ACTUAL (human README) (237 words, capped at 300)

web-fragments

Overview

The web fragments library provides a Python and Django implementation for
managing fragments of web pages. In particular, this library refactors the
fragment code from XBlock into a standalone implementation.

A Django view subclass called FragmentView is provided which supports three
different ways of rendering a fragment into a page:

the fragment can be rendered as a standalone page at its own URL

the fragment can be rendered into another page directly from Django

the fragment can be returned as JSON so that it can be rendered client-side

The rationale behind this design can be found in
OEP-12
.

The intention is that a client-side implementation will be provided in a
subsequent version. This should provide JavaScript code to request fragements
over AJAX and then dynamically update the current page. This logic will be a
refactoring of the current implementation in edx-platform for rendering XBlocks.
It is also intended that this functionality will enhance the capabilities
around dependency loading.

License

The code in this repository is licensed under the AGPL 3.0 unless otherwise
noted.

Please see
LICENSE.txt
 for details.

How To Contribute

Contributions are very welcome. Please read
the Open edX Contributing Guide
 for details.

Reporting Security Issues

Please do not report security issues in public. Please email
security@openedx.org
.

Getting Help

Have a question about this repository, or about Open edX in general?  Please
refer to the Open edX guide to
Getting Help
.

---

## V0_baseline (sonnet) (909 words, capped at 300)

# web-fragments

**web-fragments** is a small Django library for building composable HTML "fragments" — reusable pieces of a page that carry their own markup *and* their own resources (CSS, JavaScript, inline scripts) along with them. It's especially useful when you need to render the same piece of UI both as part of a larger page and as a standalone response (for example, when serving content to an AJAX/XHR request, a modal, or a widget embedded via an iframe).

Instead of manually tracking which `<link>` and `<script>` tags a partial template needs, you attach those resources directly to a `Fragment` object. The fragment can then render its body, head, and foot resource blocks independently, so a calling template or view can place them in the correct spots in the surrounding page — or, when there is no surrounding page, the fragment can render itself as a complete standalone HTML document.

## Installation

Add the app to your Django project:

```python
INSTALLED_APPS = [
    ...
    "web_fragments.apps.WebFragmentsConfig",
]
```

## Core concepts

### `Fragment`

`Fragment` (in `web_fragments/fragment.py`) is the central data structure of the library. It represents a chunk of rendered content plus any CSS/JS resources it depends on.

Key responsibilities:

- **Content** — `add_content(content)` sets/appends the fragment's HTML body.
- **Resources** — CSS and JavaScript can be attached either as inline text or as external URLs:
  - `add_css(text)` / `add_css_url(url)`
  - `add_javascript(text)` / `add_javascript_url(url)`
  - `add_resource(text, mimetype, placement=None)` / `add_resource_url(url, mimetype, placement=None)` for arbitrary resource types and explicit placement control (e.g. head vs. foot).
- **Composition** — fragments can absorb resources from other fragments, which is useful when a page is assembled out of several sub-fragments:
  - `add_fragment_resources(fragment)` merges resources from a single other fragment.
  - `add_resources(fragments)` merges resources from a list of fragments.
- **JS initialization hooks** — `initialize_js(js_func, json_args=None)` registers

[... truncated at 300 words, 909 total]

---

## V0_baseline (openai) (1014 words, capped at 300)

# web-fragments

`web-fragments` is a Python/Django-oriented library for building reusable HTML fragments together with the CSS, JavaScript, and other resources they require.

A `Fragment` collects:

- HTML content for a page body
- Resources such as inline CSS, inline JavaScript, and external URLs
- Resource placement information
- JavaScript initialization calls
- Resources contributed by nested or related fragments

Fragments can then be rendered as separate body, head, and footer HTML sections, or served through a Django `FragmentView`.

## Core concepts

### `Fragment`

`Fragment` is the main container for a reusable UI fragment.

It can hold HTML content and the assets necessary to display or initialize that content. A fragment can also incorporate resources from other fragments, making it useful for composing larger pages from independent components.

Common methods include:

| Method | Purpose |
| --- | --- |
| `add_content(content)` | Add HTML content to the fragment body. |
| `add_css(text)` | Add inline CSS. |
| `add_css_url(url)` | Add a stylesheet by URL. |
| `add_javascript(text)` | Add inline JavaScript. |
| `add_javascript_url(url)` | Add a JavaScript file by URL. |
| `add_resource(text, mimetype, placement=None)` | Add a general inline resource. |
| `add_resource_url(url, mimetype, placement=None)` | Add a general external resource. |
| `initialize_js(js_func, json_args=None)` | Register a JavaScript initialization call. |
| `add_fragment_resources(fragment)` | Add only the resources from another fragment. |
| `add_resources(fragments)` | Add resources from multiple fragments. |
| `body_html()` | Render the fragment body HTML. |
| `head_html()` | Render resources intended for the document head. |
| `foot_html()` | Render resources intended for the document footer. |
| `resources_to_html(placement)` | Render resources for a specific placement. |
| `to_dict()` / `from_dict(...)` | Serialize and restore a fragment representation. |

### `FragmentView`

`FragmentView` is a Django `View` for serving fragments.

Subclasses

[... truncated at 300 words, 1014 total]

---

## V1_anon_name (sonnet) (928 words, capped at 300)

# web-fragments

`web-fragments` is a lightweight Django library for building and rendering **HTML fragments** — self-contained pieces of markup that carry their own CSS and JavaScript resources. It's designed for situations where you need to render a reusable piece of UI (a "fragment") either as part of a larger page or as a standalone HTML document, without duplicating resource-loading logic across your views and templates.

This is especially useful for pluggable UI components, XBlock-style content, widgets, or any system where different parts of an application need to render independently but still need to declare their own stylesheets and scripts.

## Installation

```bash
pip install sample-project
```

Add the app to your Django settings:

```python
INSTALLED_APPS = [
    ...
    "web_fragments.apps.WebFragmentsConfig",
]
```

## Core Concepts

### `Fragment`

A `Fragment` represents a piece of renderable content (`body_html`) along with any number of associated resources — inline or linked CSS and JavaScript, and optional JS initialization calls. Fragments can be composed: a parent fragment can pull in the resources of one or more child fragments, so you can build up a page from independently-rendered pieces without losing track of what CSS/JS they each require.

Key responsibilities of `Fragment`:

- Hold the main `content` (HTML body) of the fragment.
- Accumulate additional `resources` — CSS or JavaScript, either inline text or external URLs.
- Track resource "placement" (e.g. head vs. body/foot) so a consuming template can decide where each resource should be inserted.
- Serialize to/from plain dictionaries (`to_dict` / `from_dict`) so fragments can be passed across process boundaries (e.g. stored in cache, sent over the wire, or handled by another service).
- Attach a JavaScript initialization call (`initialize_js`) that should run once the fragment's markup is in the DOM.
- Render itself out as HTML via `body_html()`, `head_html()`, and `foot_html()`.

### `FragmentView`

`FragmentView`

[... truncated at 300 words, 928 total]

---

## V1_anon_name (openai) (963 words, capped at 300)

# sample-project

`sample-project` provides utilities for building reusable HTML fragments with associated CSS and JavaScript resources.

It is designed for Django-style applications: a `Fragment` collects markup and frontend assets, while `FragmentView` helps render fragments either as part of a larger response or as a standalone HTML document.

## Overview

The library centers on two main classes:

- **`web_fragments.fragment.Fragment`**  
  A container for HTML content and resources such as CSS and JavaScript. Fragments can be combined, serialized, and rendered into body, head, and footer HTML.

- **`web_fragments.views.FragmentView`**  
  A Django `View` base class for views that produce `Fragment` instances. It supports rendering a fragment within an existing request flow or as a complete standalone response.

For Django application configuration, the package also includes:

- **`web_fragments.apps.WebFragmentsConfig`**  
  The Django application configuration class.

## Fragment lifecycle

A typical workflow is:

1. Create a `Fragment`.
2. Add HTML content with `add_content()`.
3. Add CSS and JavaScript resources.
4. Optionally initialize client-side behavior with `initialize_js()`.
5. Render the fragment’s body, head, or footer HTML—or return it from a `FragmentView`.

```python
from web_fragments.fragment import Fragment

fragment = Fragment()

fragment.add_content("""
<section class="welcome-card">
  <h1>Welcome</h1>
  <p>This content is supplied by a reusable fragment.</p>
</section>
""")

fragment.add_css("""
.welcome-card {
  border: 1px solid #ddd;
  border-radius: 0.5rem;
  padding: 1rem;
}
""")

fragment.add_javascript("""
function setupWelcomeCard(options) {
  console.log("Welcome card initialized", options);
}
""")

fragment.initialize_js(
    "setupWelcomeCard",
    {"source": "dashboard"},
)
```

The resulting fragment can be rendered into different portions of a page:

```python
body = fragment.body_html()
head = fragment.head_html()
foot = fragment.foot_html()
```

## `Fragment`

### Adding content

Use `add_content()` to add HTML content to a fragment.

```python
from web_fragments.fragment import Fragment

fragment = Fragment()
fragment.add_content("<p>Hello from a fragment.</p>")
```

Call `body_html()` to obtain the fragment’s body markup.

```python
html = fragment.body_html()
```

### Adding CSS

CSS can be included inline or loaded from a URL.

```python
fragment.add_css("""

[... truncated at 300 words, 963 total]

---

## V2_length_cap (sonnet) (475 words, capped at 300)

# web-fragments

`web-fragments` is a small Django library for building **composable, reusable pieces of HTML** ("fragments") that can be rendered independently or combined into a larger page. It is especially useful when building modular UIs, embeddable widgets, or systems where multiple independent components need to contribute their own HTML, CSS, and JavaScript to a page without stepping on each other's toes.

A `Fragment` bundles together HTML content and its associated static resources (CSS, JavaScript, inline scripts). Fragments can be combined, nested, and serialized, and a `FragmentView` base class makes it easy to expose a fragment as its own Django view—either as a full standalone HTML page or as an isolated HTML snippet suitable for AJAX injection into an existing page.

## Installation

Add `web_fragments` to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "web_fragments.apps.WebFragmentsConfig",
]
```

## Core Concepts

### `Fragment`

The `Fragment` class represents a piece of renderable content along with any resources (CSS/JS) it depends on.

- `add_content(content)` — sets or appends the fragment's HTML body.
- `add_css(text)` / `add_css_url(url)` — attach inline or linked CSS.
- `add_javascript(text)` / `add_javascript_url(url)` — attach inline or linked JavaScript.
- `add_resource(text, mimetype, placement=None)` / `add_resource_url(url, mimetype, placement=None)` — lower-level resource registration for arbitrary resource types and placements (e.g. head, foot).
- `add_fragment_resources(fragment)` / `add_resources(fragments)` — pull in resources from one or more child fragments, useful when composing fragments together.
- `initialize_js(js_func, json_args=None)` — emit a JS initialization call with JSON-serialized arguments.
- `body_html()`, `head_html()`, `foot_html()` — render the fragment's content and resources for insertion at different points in a page.
- `resources_to_html(placement)` / `resource_to_html(resource)` — lower-level rendering helpers for resource lists.
- `to_dict()` / `from_dict(pods)` — serialize/deserialize a fragment, e.g. for caching or passing between processes.
- `resources()` — access the full list of registered resources.

### `FragmentView`

`FragmentView` is a Django

[... truncated at 300 words, 475 total]

---

## V2_length_cap (openai) (568 words, capped at 300)

# web-fragments

`web-fragments` is a small Django-oriented library for building reusable HTML fragments together with the CSS, JavaScript, and other resources they require.

A fragment can collect body content and resource declarations, then render those resources into appropriate HTML locations such as the document `<head>` or footer. The library also includes a Django `View` base class for rendering fragments either as standalone pages or as fragment responses.

## Requirements

`web-fragments` is designed for use in a Django project. Its application configuration is exposed as:

```python
# web_fragments.apps
WebFragmentsConfig
```

Add the application to `INSTALLED_APPS` as appropriate for your project:

```python
INSTALLED_APPS = [
    # ...
    "web_fragments",
]
```

## Core concepts

### `Fragment`

`Fragment` is the primary container for HTML content and related resources.

A fragment can contain:

- Body content
- Inline CSS and JavaScript
- External CSS and JavaScript URLs
- Arbitrary resources with a MIME type and optional placement
- JavaScript initialization calls
- Resources collected from other fragments

Key methods include:

| Method | Purpose |
| --- | --- |
| `add_content(content)` | Add HTML or content to the fragment body. |
| `add_resource(text, mimetype, placement=None)` | Add an inline resource. |
| `add_resource_url(url, mimetype, placement=None)` | Add a URL-based resource. |
| `add_css(text)` / `add_css_url(url)` | Add inline or external CSS. |
| `add_javascript(text)` / `add_javascript_url(url)` | Add inline or external JavaScript. |
| `initialize_js(js_func, json_args=None)` | Add a JavaScript initialization call. |
| `add_fragment_resources(fragment)` | Copy resource requirements from another fragment. |
| `add_resources(fragments)` | Collect resources from multiple fragments. |
| `body_html()` | Render the fragment body. |
| `head_html()` | Render resources intended for the document head. |
| `foot_html()` | Render resources intended for the document footer. |
| `to_dict()` / `from_dict(...)` | Serialize and reconstruct fragment data. |

Use

[... truncated at 300 words, 568 total]

---

## V3_paraphrase (sonnet) (862 words, capped at 300)

# web-fragments

**web-fragments** is a small Django utility library for building pages out of independently renderable "fragments" — self-contained pieces of HTML that carry their own CSS and JavaScript dependencies. It is especially useful for applications that need to serve the same piece of UI in two different contexts: embedded inside a larger page (e.g. requested asynchronously and inserted into the DOM), or rendered as a complete, standalone HTML document.

Instead of hand-wiring `<script>` and `<link>` tags into templates, a fragment collects its resources programmatically. A container page (or another fragment) can then merge in a child fragment's resources, deduplicate them, and emit them in the right place (`<head>`, inline in the body, or at the bottom of the page before `</body>`).

## Core concepts

### `Fragment`

`Fragment` (in `web_fragments/fragment.py`) is the central data structure. It represents a piece of content plus a list of resources (CSS and JavaScript) that content depends on.

Key methods:

- **`add_content(content)`** — sets/appends the HTML body of the fragment.
- **`add_css(text)` / `add_css_url(url)`** — attach inline CSS or a link to an external stylesheet.
- **`add_javascript(text)` / `add_javascript_url(url)`** — attach inline JavaScript or a link to an external script.
- **`add_resource(text, mimetype, placement=None)` / `add_resource_url(url, mimetype, placement=None)`** — lower-level, generic resource-adding methods for anything not covered by the CSS/JS helpers, with an explicit MIME type and optional placement hint (e.g. head vs. foot).
- **`initialize_js(js_func, json_args=None)`** — a convenience for adding an inline script that calls a JavaScript function with the fragment's data serialized as JSON, useful for bootstrapping client-side widgets tied to server-rendered markup.
- **`add_fragment_resources(fragment)`** — pulls in the resources of another fragment (e.g. a child fragment) into this one.
- **`add_resources(fragments)`** — bulk version of the above, for merging resources from a list of fragments.
- **`resources()`** — returns the current

[... truncated at 300 words, 862 total]

---

## V3_paraphrase (openai) (996 words, capped at 300)

# web-fragments

`web-fragments` is a Django-oriented library for building reusable HTML fragments together with the CSS, JavaScript, and other page resources they require.

A fragment can contribute markup to a page body, register resources for the document `<head>` or footer, combine resources from child fragments, and render itself either as embeddable HTML or as a standalone page through a Django view.

## Overview

The package is centered around two concepts:

- **`Fragment`** — a container for HTML content and its associated resources.
- **`FragmentView`** — a Django class-based view for rendering fragments in response to requests.

This makes it possible for a component to describe both:

1. the HTML it needs to display; and
2. the CSS and JavaScript it needs to work.

A page assembling several fragments can merge their resources and render them in the appropriate locations.

## Django application configuration

The package includes a Django application configuration class:

```python
from web_fragments.apps import WebFragmentsConfig
```

Add the application to `INSTALLED_APPS` using the package name or its configuration class, depending on your Django project conventions:

```python
INSTALLED_APPS = [
    # ...
    "web_fragments",
]
```

## Creating fragments

Import and create a `Fragment`:

```python
from web_fragments.fragment import Fragment

fragment = Fragment()
```

### Adding content

Use `add_content()` to add HTML or other content to the fragment body:

```python
fragment.add_content("<section class='welcome'>Welcome!</section>")
```

The combined body markup is available through `body_html()`:

```python
html = fragment.body_html()
```

### Adding CSS

Inline stylesheet content can be added with `add_css()`:

```python
fragment.add_css("""
.welcome {
    padding: 1rem;
    background: #f5f5f5;
}
""")
```

To reference an external stylesheet, use `add_css_url()`:

```python
fragment.add_css_url("https://cdn.example.com/site.css")
```

### Adding JavaScript

Inline JavaScript can be added with `add_javascript()`:

```python
fragment.add_javascript("""
console.log("Fragment loaded");
""")
```

External JavaScript files can be added with `add_javascript_url()`:

```python
fragment.add_javascript_url("https://cdn.example.com/site.js")
```

### Adding arbitrary resources

For resource types

[... truncated at 300 words, 996 total]
