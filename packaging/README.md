# Windows source delivery

This is an unsigned, source-only local snapshot, not an installer or a public
release. It contains the runtime Python/Web source, migrations, dependency locks,
license and operating documentation. Dependencies and Web build outputs must be
installed/built using README.md before starting the application.

Build from the full checkout:

```powershell
uv run --locked python -m scripts.build_source_bundle --output .netguardian-local/releases/netguardian-windows-source.zip
```

The destination must not already exist. The allowlist in source-files.txt is
reviewed explicitly; new source files are not automatically added. Fixed ZIP
metadata and sorted entries allow repeatable builds with the same sources and
Python compression runtime. BUNDLE_MANIFEST.json records each file's size and
SHA-256; the adjacent .sha256 file identifies the complete ZIP. These are integrity
checks, not publisher signatures.

No private keys, test suites, local credentials, databases, logs, models, installed
dependencies or legacy portrait are bundled. Tests and scripts that invoke tests
must run from the original repository. In particular, do not run pytest, pnpm test,
or PostgreSQL integration verification from this reduced source snapshot. CI is
not included. Production/source startup instructions in README.md still apply.
The legacy Streamlit UI works without the optional portrait.

Keep operator tokens outside this archive. Configure your own credentials, stable
probe-location UUID and authorized origins before use. Default-deny targets stay
unchanged. Agent control still requires verified HTTPS and OS-backed credentials;
this archive does not provision a server certificate or change trust stores.
