# freerdp

FreeRDP 3.33.1 built like Arch's `2:3.33.1-1`, with two patches for WebAuthn
redirection (`rdpewa`).

## 0001: no blocking "Touch the security key" box in the SDL3 client

Before each FIDO operation, `rdpewa` sends a "Touch the security key"
notification, then a cancel notification once the operation ends. The SDL3
client shows the first one in a blocking `SDL_ShowSimpleMessageBox` and ignores
the cancel and the 30 s timeout. So the box stays open after the touch, and
every login needs an extra OK click. No option turns it off.

The patch makes the SDL3 notification handler do nothing. The key still
blinks while it waits for the touch. With more than one key plugged in, the
key selection step loses its box too.

Upstream discussed the box in FreeRDP PR #12572 and kept it. Drop
this patch once the SDL3 client closes the box on the cancel notification or
has an option to hide it.

## 0002: no FIDO2 PIN when the server says UV is not required

For a key with a PIN and no built-in user verification, `rdpewa` asked for the
PIN on every GetAssertion. That includes sites that use the key only as a
second factor. Windows sends the relying party's choice in the request
`flags`, not in the CTAP `uv` option, and FreeRDP ignored `flags`. A
second-factor login arrives with `CTAPCLT_UV_NOT_REQUIRED_FLAG` and only
`up` set. A Windows client asks for a touch only.

With the patch, GetAssertion skips the PIN when all of these hold:

- `CTAPCLT_UV_NOT_REQUIRED_FLAG` is set
- none of the UV required, UV preferred, client PIN required and select
  credential allow UV flags is set
- the CTAP request asks for user presence and doesn't ask for `uv`

The presence check keeps a server from getting a signature with no PIN and no
touch. If the key answers `FIDO_ERR_PIN_REQUIRED`, for example with
`alwaysUv` on, or `FIDO_ERR_NO_CREDENTIALS` while it supports credProtect, the
patch asks for the PIN and tries again. Keys answer `FIDO_ERR_PIN_REQUIRED`
before asking for the touch. MakeCredential is unchanged.

Drop this patch once upstream uses the request flags to decide on the PIN.

## Rollback

Run `sudo pacman -S freerdp`, then restart running FreeRDP clients.
