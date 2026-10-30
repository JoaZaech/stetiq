# The user guide is Markdown in `docs/guide/`, rendered inside the web UI

The guide for people who use stetiq (SDK, CLI, server, `stetiq.yaml`, web UI) lives as Markdown files in `docs/guide/`. Vite bundles them into the React app at build time, and the app renders them at `/ui/help/:page` with react-markdown and remark/rehype plugins (GFM tables, heading anchors, syntax highlighting), and fenced `mermaid` blocks render as diagrams with Mermaid, loaded only on pages that have one. One copy of the docs therefore works on GitHub and ships in the wheel next to the UI, matching the app's theme and navigation without a second site to deploy.

## Considered Options

- **A separate docs site (Docusaurus, VitePress, MkDocs Material, Starlight).** Rejected for the same reason ADR 0003 rejected a separately deployed frontend: a second artifact to build, version and host, and docs that live outside the UI.
- **Docsify embedded at `/ui/help`.** No build step, but it has its own theme and navigation, so it would not match the app's look, light/dark mode or sidebar.
- **marked or markdown-it.** These produce HTML strings that we would have to sanitise and inject, and links between guide pages would not navigate inside the app.

## Consequences

- A change to the guide needs a frontend rebuild before it shows in the UI.
- Links between guide pages are written as relative `.md` links so they work on GitHub too. The renderer rewrites them to in-app routes.
