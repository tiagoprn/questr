# Security Notes

## Token-consuming endpoints: interim one-step GET-consume pattern

### Current state (interim, local-only)

Four endpoints consume a single-use credential token:

- `GET /api/v1/auth/verify-email/{token}` (signup email verification).
  Pre-existing; consumes the token on GET and returns JSON.
- `GET /api/v1/auth/me/email/confirm/{token}` (email-change confirmation).
  Interim; consumes the token on GET and returns JSON, mirroring
  `verify-email`.
- `GET /api/v1/auth/me/email/revert/{token}` (email-change revert).
  Interim; consumes the token on GET and returns JSON, mirroring
  `verify-email`.
- `POST /api/v1/auth/reset-password` with `{token, new_password}`
  (password reset). This one is already a POST and is the correct final
  API shape; it cannot be a GET-consume because it requires a new
  password a GET cannot collect. Its emailed link is an inert fragment
  carrier (`{app_url}/reset-password#token={token}`) that performs no
  state change until a frontend reads the fragment and POSTs the token.

The three GET-consume endpoints make the emailed links work today:
clicking the link consumes the token and returns a JSON response, the
same behavior `verify-email` has always had. This was chosen over
serving an interim HTML form because that form was broken (it POSTed
form-encoded data to JSON-only endpoints, returning 422) and carried a
reflected XSS (the path token was interpolated into HTML without
escaping). Removing the HTML surface eliminated both defects.

### Why this is acceptable now

The application is currently deployed on a single developer machine
only. There are no real users, no mail clients prefetching links, no
link previews, no antivirus scanners, no crawlers, and no shared
browser history or logs. Under these conditions the risks below are
theoretical, not exploitable.

### Risks of one-step GET-consume (must be eliminated before any non-local deployment)

1. **Token consumption by prefetch.** Mail clients, link previews,
   chat clients, and antivirus scanners routinely issue a GET to any URL
   in an email before the user clicks. A GET-consume endpoint burns the
   token before the user ever sees the page, locking the legitimate user
   out of verification, confirmation, or revert. An attacker who can
   trigger a GET (for example via an `<img>` tag or a crafted redirect)
   can deliberately burn a victim's token, causing a denial of service
   on the credential flow.
2. **Token leakage in URLs.** The token travels in the URL path, so it
   is recorded in access logs, reverse-proxy logs, browser history, and
   the `Referer` header to any third-party resource loaded by the page.
   A logged token is a stolen credential until it expires or is used.

### Target state: two-step fragment pattern (implement before shipping)

Every token-consuming endpoint (the four above and any future one) must
move to a two-step fragment pattern:

1. The emailed link carries the token in the URL **fragment**, never in
   the path or query string: `{app_url}/<flow>#token={token}`. Browsers
   never send fragments to the server, so no prefetch, scanner, crawler,
   log, or `Referer` ever transmits the token to the backend. The token
   lives only in the user's browser until deliberately submitted.
2. The frontend loads the page, reads the fragment with JavaScript, and
   presents a confirmation form (for reset: a new-password form; for the
   others: a single confirm button).
3. On deliberate submit, the frontend POSTs the token (and any required
   input such as `new_password`) as JSON to the API endpoint.
4. The token is consumed only by that POST. No GET endpoint receives or
   consumes the token.

### What this requires, per endpoint

- **`reset-password`**: already final. The API is `POST /reset-password`
  with `{token, new_password}` and the emailed link is a fragment
  carrier. No backend change is needed; build the frontend page that
  reads the fragment and POSTs.
- **`verify-email`**: migrate from `GET /verify-email/{token}` (consume
  on GET) to a POST endpoint taking `{token}` in the body, with the
  emailed link as a fragment carrier. Add the POST; remove or redirect
  the GET.
- **`me/email/confirm` and `me/email/revert`**: migrate from
  `GET /me/email/{confirm,revert}/{token}` (consume on GET) to POST
  endpoints taking `{token}` in the body, with the emailed links as
  fragment carriers. The previous POST endpoints existed and were
  removed when this interim GET-consume pattern was adopted; restore
  them (or add new ones) and delete the GET-consume routes.
- **Future token endpoints**: ship them as POST-with-fragment from the
  start. Never ship a GET-consume token endpoint.

### Rationale summary

The one-step GET-consume pattern was adopted as a local-only interim so
the emailed links work today without a frontend, matching the
pre-existing `verify-email` behavior. It accepts the prefetch and
URL-leakage risks because there are no real users or crawlers yet.
Before the application is exposed to any non-local environment, every
token endpoint must move to the two-step fragment pattern so that tokens
are never consumed by a GET and never leave the browser except on a
deliberate POST. This preserves the single-use, no-enumeration, and
no-prefetch-consumption security properties the credential features
depend on.
