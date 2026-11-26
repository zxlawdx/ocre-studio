---
name: vela-framework
description: Build and troubleshoot native Vela Framework desktop apps. Use when scaffolding projects, registering AppConfig, implementing views, bridge, jobs or resources, collecting assets, building installers, or configuring Vela workflows.
---

# Vela Framework

1. Identify the pinned framework revision and compare the installed package against it. The APIs here were checked against Vela 0.2.2 at commit `b02be516871e507a2f678146cb5b8a822221883d`.
2. Generate the project with `vela startproject`. In an existing repository, scaffold in a temporary directory and bring over the generated files. Generate modules with `python manage.py startapp NAME`.
3. Keep the Vela runtime, route registration, native window and packaging. Customize the shell with a blank layout and route templates.
4. Compose persistent services at startup and release them through lifecycle hooks. Use Vela jobs for long operations and events for progress and outcomes.
5. Collect, verify and test assets before building. Generate the initial automation with `python manage.py makeworkflow` and validate the frozen bundle on each target OS.

Read [architecture](references/architecture.md) when composing apps, routes, APIs or native bridges. Read [runtime](references/runtime.md) for jobs, lifecycle, hot reload, resources and persistence. Read [distribution](references/distribution.md) for assets, build automation and troubleshooting. Read [CLI](references/cli.md) for exact command arguments. Use the [composition example](examples/wsgi.py) as a scaffold adaptation.

Copy this folder into another project's `.agents/skills/vela-framework/` to reuse it. Recheck the examples against that project's framework revision.
