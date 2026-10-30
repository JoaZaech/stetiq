# Server & API Tokens

`stetiq ui` is for one person over a local tracking database. To share Knowledge Graphs with a team, run a stetiq server: the SDK, the CLI and the web UI all talk to it over HTTP, and every request carries an API Token that says who is asking and what they may do.

## Run the server

```bash
stetiq server --database-url postgresql+psycopg://stetiq@db.example.com/stetiq --host 0.0.0.0 --port 5000
```

| Option | Default | What it does |
| --- | --- | --- |
| `--database-url` / `$STETIQ_DATABASE_URL` | `sqlite:///.stetiq/server.db` | The server's database: every Knowledge Graph, Ontology Version, Construction Run and API Token it holds. A `postgresql+psycopg://` URL needs `pip install "stetiq[postgres]"`. |
| `--host` | `127.0.0.1` | The interface to listen on. Use `0.0.0.0` to accept connections from other machines. |
| `--port` | `5000` | The port to listen on. |
| `--question-mapper` / `$STETIQ_QUESTION_MAPPER` | `none` | Maps Competency Questions that have no query onto the Ontology: `anthropic` (needs `stetiq[llm]`), `module:attr`, or `none`. In server mode only the server's mapper applies. |

The server never connects to your graph database. Observations and custom Evaluators run in the SDK process, next to your graph credentials, and only their results reach the server. The server computes everything else itself, such as Gate outcomes and the actor in the audit log.

The server speaks plain HTTP. To serve it over `https://`, put it behind a reverse proxy that terminates TLS.

## Issue API Tokens

An API Token authenticates one user to the server and grants `read` or `edit` permission per Knowledge Graph. An administrator issues tokens with the `stetiq token` commands. They run directly against the server's database, not over HTTP, so pass the same `--database-url` (or `$STETIQ_DATABASE_URL`) the server uses:

```bash
stetiq token create ada --grant support=edit --grant billing=read --database-url postgresql+psycopg://stetiq@db.example.com/stetiq
```

```text
Created token 3f9c1a2b for ada (billing=read,support=edit):
stq_3f9c1a2b_...
```

The last line is the token. It is shown only once: the server stores a hash of it, never the token itself. Hand it to its user over a channel you trust.

There is no HTTP endpoint or web page that issues tokens. Whoever can reach the server's database already controls everything the server holds, so issuing tokens there adds no new way in.

### Permissions

Each `--grant KNOWLEDGE_GRAPH=read|edit` gives the token one permission on one Knowledge Graph. Repeat `--grant` for more.

| Permission | Allows |
| --- | --- |
| `read` | Every read: listing and opening the Knowledge Graph, its Ontology Versions, Construction Runs, Use Case, Observations and Promotions. |
| `edit` | Everything `read` allows, plus every change: registering an Ontology Version, starting a Construction Run, editing the Use Case, recording an Observation, moving an Alias or promoting. |

- `edit` includes `read`.
- `*` grants every Knowledge Graph, including ones created later: `--grant '*=edit'`.
- Creating a Knowledge Graph needs `edit` on its name (or on `*`).
- Listing Knowledge Graphs shows only those the token can read. A Construction Run or Observation outside its grants answers exactly like one that doesn't exist.
- The audit log records the token's user as the actor of every change. In server mode the actor the SDK sends (`$STETIQ_ACTOR`) is ignored.

A "user" is just the name on a token: there is no user directory, and permissions live on each token. To change someone's permissions, issue a new token and revoke the old one.

### List and revoke tokens

```bash
stetiq token list --database-url postgresql+psycopg://stetiq@db.example.com/stetiq
stetiq token revoke 3f9c1a2b --database-url postgresql+psycopg://stetiq@db.example.com/stetiq
```

`stetiq token list` shows each token's id, user, status and grants, never the token itself. A revoked token is refused from its next request on. A lost token can't be recovered: revoke it and issue a new one.

## Point the SDK and CLI at the server

Set the tracking URI to the server's `http(s)://` address and the API Token in `$STETIQ_TOKEN`:

```bash
export STETIQ_TRACKING_URI=https://stetiq.example.com
export STETIQ_TOKEN=stq_3f9c1a2b_...
```

An `http(s)://` tracking URI is remote mode: the SDK and CLI send every request to that server with the token. A `sqlite:///` or `postgresql://` one is local mode, which needs no token. The CLI takes the token only from `$STETIQ_TOKEN`, so it never appears on a command line:

```bash
stetiq kg list
stetiq kg list --tracking-uri https://stetiq.example.com
```

In Python, `Client()` reads the same variables, or takes them as arguments:

```python
import stetiq

client = stetiq.Client()  # $STETIQ_TRACKING_URI and $STETIQ_TOKEN
client = stetiq.Client("https://stetiq.example.com", token=my_token)
```

A request without a token fails with *This stetiq server requires an API token (set STETIQ_TOKEN)*, and one with an unknown or revoked token with *Invalid or revoked API token*. A request the token's grants don't cover fails with a permission error naming the token, its user, the permission it lacks and the Knowledge Graph.

## Sign in to the web UI

The server serves the web UI at `/ui`, for example <https://stetiq.example.com/ui>. Open it, paste your API Token on the sign-in page and choose **Sign in**. The web UI uses the same tokens: it never issues one. **Settings** shows who you are signed in as and what you may read or edit.

The browser keeps the token in a cookie that page scripts can't read, and sends it with every request from the web UI. **Sign out** in Settings makes the browser forget it. The token itself stays valid until an administrator revokes it, and once it is revoked the web UI asks you to sign in again.

Help is readable without signing in.

Under `stetiq ui` there is nothing to sign in to: local mode has no API Tokens, and every action is recorded under your OS user (or `$STETIQ_ACTOR`). `stetiq ui` refuses an `http(s)://` tracking URI and tells you to open the server's own web UI instead.
