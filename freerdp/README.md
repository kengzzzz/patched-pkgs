# freerdp

FreeRDP 3.33.1 built like Arch's `2:3.33.1-2`, with two patches for WebAuthn
redirection.

## 0001: no blocking "Touch the security key" box in the SDL3 client

The SDL3 client shows the touch notification in a blocking message box and
ignores the cancel. Every login needs an extra OK click.

The patch makes the SDL3 notification handler do nothing. The key still
blinks. With several keys plugged in, the key selection box goes too.

Upstream kept the box in FreeRDP PR #12572. Drop this patch once the SDL3
client closes the box on cancel or can hide it.

## 0002: no FIDO2 PIN when the server says UV is not required

FreeRDP asked for the PIN on every GetAssertion, even for second-factor
logins. Windows sends that choice in the request `flags`, which FreeRDP
ignored.

The patch skips the PIN when all of these hold:

- `CTAPCLT_UV_NOT_REQUIRED_FLAG` is set
- no flag asks for or prefers UV or a client PIN
- the request asks for user presence and not for `uv`

The presence check means a server never gets a signature without a PIN or a
touch. If the key answers `FIDO_ERR_PIN_REQUIRED`, or `FIDO_ERR_NO_CREDENTIALS`
with credProtect, the patch asks for the PIN and tries again. MakeCredential
is unchanged.

Drop it once upstream uses the request flags to decide on the PIN.

## Rollback

Run `sudo pacman -S freerdp`, then restart running FreeRDP clients.
