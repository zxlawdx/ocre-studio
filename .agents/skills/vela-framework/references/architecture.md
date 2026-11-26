# Architecture, apps and API

Keep metadata in `config/settings.py`. Return a `VelaApp` from `config/wsgi.py` and call its `run()` from the existing project entrypoint. Register `AppConfig(name="editor", module="apps.editor")` explicitly. The registry reads `views_module`, `urls_module`, `api_module`, roots and hidden imports. Views register named routes with `register_routes(router)`, calling `router.add`.

Render templates with `vela.template_engine.render_template(path, router=params["router"])`. Templates escape data and resolve files with `static()`. Blank layouts support an app-designed editor shell and preserve delegated `data-vela-link` navigation.

Vela binds the API registration context while importing the app API module. Inspect the upstream API decorators before adding HTTP routes. Keep the API on loopback and disable docs when distributed. A `BaseBridge` subclass receives `router` and `config`. Add narrowly scoped methods for JavaScript and keep filesystem choices in native dialogs.
