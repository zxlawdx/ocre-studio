# Lifecycle, services and jobs

Declare stateful services in AppConfig's `persistent_modules` and only refresh view modules. Bridge custom initialization can be supplied through a callable that accepts the framework's router and config. Attach shutdown hooks with `application.lifecycle.on_shutdown`.

Instantiate `JobManager(io_workers=1, max_pending_jobs=1)` for jobs that must share one CUDA context. Submit with `mode="io"` and use a future callback. For Python CPU tasks, explicitly enable CPU workers before selecting process mode. Shutdown the manager and release resources after jobs finish. Use cooperative cancellation in the processing callback where possible.

Send JSON-serializable notifications using the Bridge `emit` or `application.events.emit`. JavaScript receives `vela:event` with `event.detail.name` and `event.detail.payload`. Dispose listeners in `VelaPage.beforeUnmount` or via its signal.

Publish temporary immutable snapshots via `application.resources.publish` and open trusted backend paths using `open_path`. Use `SQLiteStore` and `dbmigrate` for durable application state if appropriate. Restart sessions when persistent module code changes.
