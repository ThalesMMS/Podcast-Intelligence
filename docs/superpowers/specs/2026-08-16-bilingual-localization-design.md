# Bilingual Localization Design

**Status:** Approved in chat on 2026-08-16

## Objective

Make English the source language for the repository while giving the web application a complete, accessible `en-US` / `pt-BR` interface toggle. The interface locale and the language selected for episode transcription and generated content remain separate concepts.

## Goals

- Translate all repository documentation and human-readable source text to English.
- Provide complete `en-US` and `pt-BR` catalogs for the web interface.
- Detect the browser language on the first visit, map any `pt*` language to `pt-BR`, and use `en-US` for every other language.
- Persist an explicit or detected interface locale locally.
- Keep the episode language selector independent from the interface locale.
- Localize visible copy, accessibility labels, dynamic messages, date and number formatting, and user-facing failures.
- Keep the existing application behavior, API contracts, data model, routes, and technical identifiers stable.

## Non-goals

- Locale-prefixed routes such as `/en-US/episodes/...`.
- Server-side locale negotiation, cookies, translated URLs, or search-engine-specific locale metadata.
- More than the two approved interface locales.
- Translating podcast titles, imported transcripts, episode metadata, or other user/provider content.
- Changing an episode's transcription or generated-content language when the interface toggle changes.
- Renaming schema fields, enum values, database columns, environment variables, CLI flags, API routes, or other machine-facing contracts.

## Localization Architecture

The frontend will use a small in-repository localization layer rather than a third-party internationalization dependency. This keeps the implementation proportional to a local application with two locales and no locale-aware routing.

The localization layer will be split by responsibility:

- `frontend/lib/i18n/locales.ts` defines the supported locale union, default locale, storage key, validation, browser detection, and resolution precedence.
- `frontend/lib/i18n/messages.ts` defines the English source catalog and a Portuguese catalog that is statically required to contain the same keys.
- `frontend/lib/i18n/provider.tsx` owns the active locale, persistence, document-language synchronization, translation lookup, interpolation, and localized formatting helpers.
- `frontend/components/locale-toggle.tsx` renders the accessible locale control without owning locale state.

The English catalog is the structural source of truth. Its keys define the `MessageKey` type, and the Portuguese catalog must satisfy `Record<MessageKey, string>`. Missing or extra Portuguese keys therefore fail typechecking. Message interpolation uses named placeholders. Pluralized messages use paired `.one` and `.other` keys selected through `Intl.PluralRules`; both approved locales use those categories for the application counts currently displayed.

Components consume localization only through `useI18n()`. They must not import a locale catalog directly or keep visible copy in component-local constants. Content values returned by the API remain data and must not pass through the interface translator.

## Locale Resolution and Persistence

The provider uses this precedence on the client:

1. A valid value stored at `podcast-intelligence.locale`.
2. `pt-BR` when `navigator.language` starts with `pt`, case-insensitively.
3. `en-US` for every other browser language or when browser language is unavailable.

Invalid stored values are ignored and replaced with the resolved supported locale. The resolved first-visit locale is persisted, and every later toggle selection is persisted immediately. Storage failures are non-fatal: the in-memory locale still changes for the current session.

The server render uses a stable `en-US` snapshot. Client-side resolution occurs after hydration so server and initial client markup agree. The provider then updates the UI and sets `document.documentElement.lang` to the active locale. The root layout declares `en-US` as its static fallback. A brief post-hydration locale update is acceptable; hydration warnings or mismatches are not.

Locale changes affect only presentation state. They do not reload the route, clear component state, repeat API mutations, or alter the current episode-language selection.

## Toggle Experience

The toggle is an accessible two-option segmented control labeled with the exact locale identifiers `en-US` and `pt-BR`.

- On desktop, it appears at the bottom of the fixed sidebar above the local-workspace status.
- At widths where the sidebar becomes a horizontal header, it remains visible in that header while the workspace status stays hidden.
- The active option has a programmatic selected state and a visible active style that does not depend only on color.
- Both options are keyboard reachable, have localized accessible naming, and use native buttons so Enter and Space work without custom keyboard emulation.

Changing the toggle updates the whole visible interface, document language, date and number formatting, and persisted preference. It does not update the import form's transcription-language field.

## Presentation and Formatting

The catalogs cover every application-owned visible string, including:

- headings, navigation, tabs, buttons, labels, helper text, empty states, and loading states;
- placeholders, tooltips, status labels, import-source labels, and export labels;
- `aria-label`, dialog labelling, screen-reader-only text, and other accessibility copy;
- chat suggestions and speaker-editing copy;
- pluralized counts and messages with runtime values;
- client validation, playback, polling, and request-failure messages.

Dates and user-visible numbers use `Intl` with the active interface locale. Media durations and transcript timecodes preserve their established semantic format and are not treated as locale state. Transcript search operates on transcript content and remains independent of the interface locale.

Next.js static metadata is written in English because it cannot react to the client-only locale in this design. Interactive page content is fully bilingual.

## Error Presentation

Backend exception text and internal diagnostic messages use English as the repository source language. The frontend does not render arbitrary backend text directly in normal error surfaces.

Known API error codes and HTTP statuses are mapped to catalog keys. Each operation also supplies a localized contextual fallback, such as loading the library, opening an episode, saving a speaker, or generating a summary. Validation and client-side media errors use stable client error codes rather than embedded display sentences. Processing-job failures use `error_code` mappings when available and a localized generic failure otherwise.

Unexpected technical details remain available to developers through console logging, while the user sees a safe localized fallback. This avoids leaking English diagnostics into the `pt-BR` interface and avoids coupling the API to the active UI locale.

## Content-Language Independence

The import form retains a separate episode-language selector. Its state is neither initialized from nor updated by the interface toggle. Existing API language fields and BCP 47 normalization remain unchanged.

AI system prompts are authored in English, but their output instructions follow content intent:

- summaries use the transcript's language;
- grounded answers use the user's question language;
- citations preserve source wording;
- the interface locale is never sent to the language model.

Demo content and general test fixtures become English and use matching English language metadata. Tests dedicated to the Portuguese catalog intentionally retain Portuguese expected strings.

## Repository-wide Translation Scope

English becomes the repository source language for:

- `README.md`, `GETTING_STARTED.md`, `VALIDATION.md`, security and operational guidance;
- all files under `docs/`, including ADRs, API documentation, deployment guidance, architecture, providers, and limitations;
- frontend source outside the `pt-BR` catalog;
- backend prompts, error messages, demo data, export headings, comments, docstrings, and command descriptions;
- tests, fixtures, sample questions, and expected English source messages;
- comments and descriptions in configuration, Compose, scripts, and automation files when Portuguese text is present.

Technical tokens and content that are not natural-language Portuguese remain unchanged. Examples include `pt`, `pt-BR`, test data specifically exercising Portuguese, URLs, identifiers, and protocol/schema field names.

## Testing Strategy

Frontend unit tests will cover:

- supported-locale validation and browser-language mapping;
- stored-locale precedence, invalid stored values, storage failures, and persistence;
- locale switching and `<html lang>` synchronization;
- translation lookup, placeholder interpolation, plural selection, and catalog parity through typechecking;
- representative rendering in both locales for the shell, dashboard, episode workspace, dialogs, statuses, errors, and accessibility copy;
- toggle semantics, selected state, keyboard activation through native controls, and mobile/desktop presence;
- localized date formatting and error-code presentation;
- proof that changing the interface locale does not change the episode-language field.

Existing backend and frontend tests will be updated to use English source fixtures where Portuguese is not the subject under test. Backend tests continue to verify prompt safety, structured model output, exports, and API behavior after the textual translation.

## Validation and Completion Criteria

The implementation is complete only when all of the following are true:

1. A repository-wide residual scan finds no unintended Portuguese outside the `pt-BR` catalog and explicit localization tests.
2. The frontend formatter, linter, typechecker, full test suite, and production build succeed.
3. The backend formatter check, linter, typechecker, and full test suite succeed.
4. The application is inspected at runtime in both locales at desktop and mobile widths.
5. Browser detection, persisted preference, toggle switching, `<html lang>`, and the independent episode-language selector are verified in the running UI.
6. `FILE_MANIFEST.sha256` is regenerated after all repository changes and then verified against the final files it covers.

No claim about Docker integration, real provider calls, or external services will be made unless those checks are also run with the required services and credentials.
