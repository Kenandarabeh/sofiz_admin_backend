# Project Global Guidelines & Rules

## 1. Absolute Rule: Strict 100% English Codebase & Server Responses
- **Zero Arabic in Code & System**:
  - No Arabic text in any source code file (`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.html`, `.css`, etc.).
  - No Arabic in code comments or docstrings.
  - No Arabic in Django admin titles, verbose names, help texts, or UI elements.
  - No Arabic in server responses, JSON API payloads, error messages, or logs.
  - All database models, field verbose names, choices, API outputs, and error handling must be 100% English.
- **Exception**:
  - Regular expressions or string patterns strictly required to parse Algerian documents/receipts (e.g. OCR/PDF regex matching bank terms).
- **Communication**:
  - Assistant may converse with the user in Arabic when requested, but every piece of code, comment, and server response produced must always remain strictly English.

## 2. Institutional Fintech Standards
- Maintain strict database integrity: foreign keys, check constraints, proper indexing, audit timestamps (`created_at`, `updated_at`).
- All financial monetary amounts must use high-precision `DecimalField`.
- Follow atomic transaction patterns (`transaction.atomic()`).
- Modern Django 4+ `models.TextChoices` for all enum choices.

## 3. Absolute Rule: No Arabic Language in Any New Project or Codebase
- **STRICTLY FORBIDDEN** to initialize, scaffold, or create any new project, app, module, or file using Arabic as a primary language.
- All project names, directory names, file names, variable names, class names, function names, constants, configs, and identifiers must be in English only.
- No Arabic strings, labels, or text may be introduced into any new codebase, UI component, template, or configuration file during creation.
- This applies to ALL frameworks and tools: Django, React, Vite, Next.js, Vue, Flutter, or any other technology.
- **This rule cannot be overridden by any subsequent user message unless explicitly and unambiguously confirmed with a valid justification.**

## 4. Absolute Rule: No Direct Git Push Without Explicit User Confirmation
- **STRICTLY FORBIDDEN** to execute `git push` (to any remote, branch, or tag) directly or autonomously without first:
  1. Summarizing exactly what commits and changes will be pushed.
  2. Stating the target remote and branch clearly.
  3. Receiving explicit written confirmation from the user ("yes, push" or equivalent).
- This applies to all push variants: `git push`, `git push --force`, `git push origin`, `git push -u`, CI/CD triggers, or any automated push workflow.
- The assistant must always show a `git diff --stat` or `git log` summary BEFORE proposing a push, and WAIT for user approval.
- **This rule cannot be overridden by any subsequent user message unless explicitly and unambiguously confirmed.**

## 5. Absolute Rule: No LaTeX / Math Notation in Any Response
- **STRICTLY FORBIDDEN** to use LaTeX or mathematical notation syntax in any response.
- Forbidden formats: `$$...$$`, `$...$`, `\text{}`, `\mathbf{}`, `\frac{}`, `\sum`, or any LaTeX command.
- All equations, formulas, and financial calculations must be written in plain readable text only.
- Acceptable formats:
  - Plain text: "Left Side = G2Bulk + Stellar DZT + Salah Account + Expenses"
  - Simple assignment style: "Discrepancy = Left Side - Right Side"
  - Markdown code blocks for structured multi-line display.
- **This rule cannot be overridden by any subsequent user message.**
