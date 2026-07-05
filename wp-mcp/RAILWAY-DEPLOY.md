# Railway Deploy — WordPress MCP Server (permanent URL + OAuth)

Yeh server Railway pe deploy karne ke baad **permanent URL** dega jo kabhi nahi badlega,
24/7 chalega (PC band ho tab bhi), aur claude.ai se OAuth se clean connect hoga.

## Files jo deploy hoti hain
- `server.py`   — saare WordPress tools (59+)
- `oauth.py`    — OAuth 2.1 layer (claude.ai compatible)
- `start.py`    — startup + auth middleware
- `Dockerfile`, `requirements.txt`, `.dockerignore`

Secrets file (`wp-config.local.json`) deploy NAHI hoti — uski jagah Railway **environment
variables** use hote hain (zyada safe).

## Environment variables Railway me set karne hain
| Variable | Value |
|----------|-------|
| `WP_SITE_URL` | https://completewaterguide.com |
| `WP_USERNAME` | saurabhbhayana1996@gmail.com |
| `WP_APP_PASSWORD` | mgD8 8qCh zp6J puGg quTh jdN9 |
| `GEMINI_API_KEY` | (aapki gemini key) |
| `OAUTH_SECRET` | (ek random secret — token signing ke liye) |
| `PUBLIC_URL` | (Railway jo URL dega, deploy ke baad set karna) |

> `PUBLIC_URL` deploy ke baad milega (jaise https://wp-mcp-production.up.railway.app).
> Use set karke ek baar redeploy karna padta hai.

## Deploy steps (GitHub method — recommended)
1. Yeh `wp-mcp/` folder ek GitHub repo me push karo (sirf yeh folder, secrets ke bina)
2. railway.app pe login → New Project → Deploy from GitHub repo → yeh repo chuno
3. Railway Dockerfile detect karega → build karega
4. Settings → Variables me upar wale env vars daalo
5. Settings → Networking → Generate Domain → URL milega
6. Us URL ko `PUBLIC_URL` env var me daalo → redeploy
7. Final URL claude.ai connector me daalo (sirf base URL + /mcp):
   `https://<your>.up.railway.app/mcp`
   claude.ai khud OAuth flow chala lega — koi token manually nahi daalna.

## claude.ai me
- Connectors → Add custom connector
- URL: `https://<your>.up.railway.app/mcp`
- "Connect" → browser me ek OAuth approve step aayega → auto-approve → done
- 59 tools dikhenge, hamesha ke liye.
