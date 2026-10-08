# Little Atlas Web

A private online notebook with an English interface. Every new email account starts empty. Write **Content** and click **+** to open an editable article; the initial title and classification are generated automatically and remain editable.

[Open Little Atlas](https://little-atlas-notebook.c8fmkxqy6h.chatgpt.site/)

## Features

- Email and password registration, login, and seven-day sessions using Better Auth and Cloudflare D1.
- Cloud documents belong to the account, so the same sign-in can open saved notes from a computer, phone, or tablet.
- Articles support paragraph, heading, and subheading blocks with a clickable document outline, continued editing, and Markdown export. Notes can contain up to 200,000 characters.
- Debounced cloud autosave shows its actual save state. Revision checks reject stale-device edits, preserving the current draft for review instead of silently overwriting newer work.
- Automatic title and chapter inference from English or Chinese content, without a model call. The original wording is preserved; Chinese notes are not silently translated.
- Source-linked English Wikipedia research and licensed Wikimedia Commons images. Research includes later sections instead of stopping at eighteen sentences; very long sources are bounded. Ordinary searches use public APIs and do not consume OpenAI tokens.
- Search a whole paragraph: the main topic is extracted before researching it. Saving content and opening an existing entry without pictures automatically looks up licensed reference images in the background. Unavailable images can be retried with **Find images**; your text is saved immediately and stays unchanged.
- Paste a public HTTPS article link to import readable English passages. Other sites retain their original source and copyright; articles that require login or browser scripts may not be readable.
- A selection pen saves the exact passage you drag over. Yellow and red pens persist annotations on saved text.
- Selected research is appended to an open note while retaining its headings and customized title; otherwise it creates a new note.
- Searchable contents, editing, deletion, and browser speech input when supported by the browser.

Accounts use email as their login identifier. Registration does not send a verification email; SMTP-based verification and password reset delivery are not configured in this version. Passwords are hashed by Better Auth, and sessions use HTTP-only cookies. Each entry API checks the authenticated account before every read or write.

## Development

Use Node **22.13 or newer** and npm. Run these commands from the `web` directory:

```sh
npm run install:ci
node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))"
```

Copy the generated random value into a new, ignored `web/.dev.vars` file:

```text
BETTER_AUTH_SECRET=<paste the generated value; at least 32 characters>
BETTER_AUTH_URL=http://127.0.0.1:5173
```

Build once to generate the local Worker configuration, then initialize a **new local database** with both tracked migrations:

```sh
npm run build
npx wrangler d1 execute DB --config dist/server/wrangler.json --local --persist-to .wrangler/state --file drizzle/0000_yummy_kinsey_walden.sql
npx wrangler d1 execute DB --config dist/server/wrangler.json --local --persist-to .wrangler/state --file drizzle/0001_slippery_george_stacy.sql
npm run dev
```

Open **http://127.0.0.1:5173**. Use that exact origin so login matches `BETTER_AUTH_URL`. Apply each migration once per database. An existing pre-notebook local database needs only migration `0001`; its saved notes are preserved. The `DB` binding is named `site-creator-d1` in the generated configuration; its placeholder ID supports local development. Both the preview and the commands above use ignored `.wrangler/state` storage. Local accounts and entries start empty.

After changing the schema, use `npm run db:generate` and apply each new SQL file with the same local command and its new `--file` path. Keep `.dev.vars`, credentials, and `.wrangler` state out of Git.

## Deployment

The [original website](https://little-atlas-notebook.c8fmkxqy6h.chatgpt.site/) uses the Sites source, build, and publication workflow. Sites applies the tracked SQL migrations to its hosted D1 database during publication. The desktop app in the parent directory is separate.

A clone needs its **own** hosting project, D1 database, deployment configuration, and runtime secrets. The checked-in `.openai/hosting.json` describes the original Sites project; it does not provision another deployment. Set a fresh `BETTER_AUTH_SECRET` and `BETTER_AUTH_URL` to your deployed HTTPS origin, and connect your own database to the `DB` binding. If publishing through Sites, use that project's supported source and publication workflow.

## Checks

```text
node node_modules/typescript/bin/tsc --noEmit
node --test tests/knowledge.test.mjs tests/webpage.test.mjs tests/entry-data.test.mjs tests/notebook.test.mjs
```

For a disposable local D1 test database, set `ATLAS_TEST_URL` to the running preview and run `node --test tests/auth-live.test.mjs`. This tests real registration, login, cookie sessions, automatic organization, and isolation between two users. Test account identifiers are disposable and test entries are removed.

`node --test tests/notebook-live.test.mjs` checks heading and metadata persistence, edits from two separate sessions, stale-write rejection, longer articles, and private account isolation. It creates and deletes only disposable diagnostic accounts and requires a running preview with all migrations applied.

`node --test tests/nyx-live.test.mjs` checks full-paragraph research, automatic licensed images, thumbnail loading, and preservation of saved images and markings. Integration checks require internet access and remove their disposable test accounts afterward. Use a local test database for combined account checks.

## Attribution

Application code is MIT licensed. Wikipedia excerpts retain their original source links and CC BY-SA terms. Each Commons image retains its source, author, and license. Research is offered for the user to review; it is only added to a notebook when selected.
