# Writing the workshop site (`docs/`)

The attendee guide is a MkDocs Material site in `docs/`, published to GitHub Pages by `.github/workflows/docs.yml`.
Pages follow the Workshop Studio style: one page per lab part, a concept first, then steps, then what you should see.

## Preview locally
```
uv run --python 3.12 --with-requirements requirements-docs.txt mkdocs serve      # http://127.0.0.1:8000
uv run --python 3.12 --with-requirements requirements-docs.txt mkdocs build --strict
```

## Page template (lab part)
~~~~markdown
# Part N: Title

!!! time "15 minutes"

## What you'll learn
- 2–4 bullets, each tied to an AgentCore feature.

## Concepts
Short prose (2–4 paragraphs) explaining the idea *before* the commands: what problem it solves for Dezerv,
how the AgentCore feature works, and why it is built this way. Include a diagram where it helps:

![Alt text](../diagrams/<name>.drawio)

## Steps
### 1. Do the first thing
One sentence on why, then the command:
```bash
make gateway
```
??? example "Expected output"
    ```text
    (real or representative output; trim to the lines that matter)
    ```

## Verify
```bash
make verify-labA-partN
```
!!! success "You should see"
    ...

## What just happened
Recap of the mechanism in 3–5 bullets.

!!! tip "Behind?"
    `make solution-partN` brings you to the end of this part.

## Troubleshooting (optional, per-part issues only)
~~~~

## Conventions
- Admonitions: `note` (context), `info` (AgentCore feature detail), `tip` (shortcuts, catch-up), `warning` (gotchas),
  `danger` (anything touching guardrails or secrets), `success` (expected result), `question` (discussion prompt for the room),
  `time` (custom, duration). Collapsible: `??? example "Expected output"`.
- Commands are always `make` targets run from the repo root, exactly as in `Makefile`. Never invent targets or flags.
- Facts (numbers, ids, file paths, outputs) must come from the code, `CLAUDE.md`, `INSTRUCTOR.md` or `FINDINGS.md`.
  If you cannot confirm an output, label it "representative output".
- Never print or show `.env`, `.labA.json` or secrets. All data is synthetic: say so where real-looking PII appears.
- Link files in the repo with the full GitHub URL only if needed; prefer `inline/code/paths`.
- Use `=== "Tab"` blocks for alternatives (for example "Go installed" / "No Go").

## Diagrams (draw.io)
- Source files live in `docs/diagrams/*.drawio` and are embedded with normal image syntax: `![Alt](../diagrams/x.drawio)`.
  The `mkdocs-drawio` plugin renders them in the browser, so there is no export step. Edit them in draw.io desktop,
  app.diagrams.net, or the VS Code "Draw.io Integration" extension.
- **The alt text must equal the diagram's page name** (`<diagram name="...">`): the plugin uses it to pick the page, and a mismatch or an apostrophe breaks the build.
- One `<diagram>` page per file. Keep diagrams under about 1240 x 700.
- Style, copied from `docs/diagrams/lab-a-architecture.drawio`:
  - Account boundary: `shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud_alt`.
  - AWS service icons: `shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<name>` (48 x 48), with `fillColor` by category:
    Bedrock / AgentCore `#01A88D` (`bedrock`), Lambda `#ED7100` (`lambda`), DynamoDB `#C925D1` (`dynamodb`),
    S3 `#7AA116` (`s3`), CloudWatch `#E7157B` (`cloudwatch_2`), SSM `#E7157B` (`systems_manager`), Cognito `#DD344C` (`cognito`).
    People: `shape=mxgraph.aws4.user`.
  - Logical groups (rounded containers): agent `#E6F6F7`/`#01A88D`, Gateway `#F2EEFB`/`#8C4FFF`,
    Lambda targets `#FDF1E7`/`#ED7100`, policy/Cedar highlight `#FFF4E5`/`#FF9900`, forbidden/decoy `#FDECEE`/`#DD344C` dashed,
    Go components `#E8F6FC`/`#00ADD8`.
  - Edges: orthogonal; solid for the request path, dashed for side effects (logs, state); 10–11 px labels.
- Check that a diagram renders: build the site and open the page (or screenshot it with headless Chrome).
