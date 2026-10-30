# API Tokens are issued by an administrator against the server's database

In server mode every API request carries an API Token (`Authorization: Bearer ...`). Each token belongs to one user and grants `read` or `edit` permission per Knowledge Graph (`edit` implies `read`; `*` grants every Knowledge Graph, including ones not yet created). GET requests need `read`; anything that changes state, such as registering an Ontology Version, starting a Construction Run or moving an Alias, needs `edit`. The audit log records the token's user as the actor, and the server ignores the actor the SDK sends. We chose not to build an HTTP endpoint or login flow for issuing tokens. Instead an administrator runs `stetiq token create USER --grant KG=read|edit --database-url ...` directly against the server's database. Whoever can reach that database already controls everything the server holds, so this adds no new trust boundary and avoids a bootstrap "first admin" problem. Local mode stays tokenless, because the user already owns the database file.

## Consequences

- The server stores only a SHA-256 hash of each token. The secret is printed once, and a lost token is revoked (`stetiq token revoke ID`) and reissued, never recovered.
- There is no user directory. A "user" is just the name on its tokens, and permissions live on the token rather than on the user.
- The server fails closed. A route whose Knowledge Graph it cannot tell from the path (`name`, `run_id` or `observation_id`) rejects every token, so new routes must use those path parameters or authorize themselves.
- To move to SSO or OIDC later, swap `TokenRegistry.authenticate` for a verifier with the same contract (token in, user and grants out).
- The web UI under `/ui` reuses the same tokens: a user pastes an existing API Token at `/ui/login`, and the server keeps it in an HttpOnly cookie for later pages. This is not a token-issuing flow. No token is ever created or handed out over HTTP.
- A run or Observation id that the token cannot read gets the same 404 as an unknown id, so ids do not reveal what exists outside the token's grants.
