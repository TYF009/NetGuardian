# Public test-only TLS identity

These files are disposable test fixtures for `netguardian.test`, not production
credentials. The private key is intentionally public. Never deploy it or add the
certificate to a system trust store. Integration tests load it into a temporary
in-process SSL context only. Generated with the local Git-bundled OpenSSL on
2026-11-05 with a ten-year validity window; renew the fixture before expiration.
