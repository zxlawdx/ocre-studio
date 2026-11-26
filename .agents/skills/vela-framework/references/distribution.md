# Assets, packaging and troubleshooting

Collect per-app scripts, CSS and images with `collectstatic`; use `assets verify` to verify the manifest and bundle inputs. Deploy local assets without CDN dependencies. Build output lives in `dist/` and intermediate files in `.vela-build/`.

Run `doctor`, `self-test`, `buildapp --dry-run`, then the native build with the verified GUI backend. Use native Windows runners for Windows and suitable Linux runners for Linux, respecting the bundle's glibc baseline. Check installer tools, native Qt libraries, platform plugins and frozen imports. Exercise the executable with the same assets and backend used in distribution.

Generate CI using `makeworkflow`, then review permission scopes and verify artifacts before allowing release publication. If the window is blank, verify the browser engine, loopback server, template output and asset URLs, then check WebView logs. A missing transitive dependency can raise `ModuleNotFoundError` during WSGI import. Inspect the exception's module name before assuming the entrypoint is absent.
