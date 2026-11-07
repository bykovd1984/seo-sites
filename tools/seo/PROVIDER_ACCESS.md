# Shared provider access

All chats and agents submit ToolsPD/Semrush research through the same installed
`seo-research` MCP server or its equivalent CLI. Do not open ToolsPD/Semrush in
an agent browser, call a private provider endpoint, create another profile, or
start an independent collector to bypass a paused/busy queue or daily limit.

The current shared entry point is:

```powershell
python C:\Dev\seo-sites\tools\seo\launch.py serve
```

Each MCP client can have its own lightweight process. They use the same configured
data directory, durable SQLite job queue, cached evidence and independent worker.
`research_keywords` returns a durable job ID; use `job_status` to follow it and
`get_keywords` to read results. A paused or partially completed job is not success.
`provider_status` reports the local pause, shared quota, exclusive slot and queue
without contacting ToolsPD. The equivalent console operation is:

```powershell
python C:\Dev\seo-sites\tools\seo\launch.py call provider_status
```

The worker serializes jobs. Before reserving a provider attempt or opening its
browser, it acquires a machine-wide exclusive ToolsPD slot, shared across app
processes, projects, data directories and service domains. A busy slot leaves the
job queued and consumes no attempt. Crashes release the OS lock. Diagnostic and
interactive-login commands use the same slot. Old service tabs are closed during
failover so their background polling does not overlap the next service. The
legacy direct browser collection/login entry point is disabled; saved-report
imports and read-only archive preparation remain available.

Use one owner profile and keep the shared pause/delay/quota settings. Never reset
or refund the attempt ledger. Closing a chat does not delete durable jobs. Source
updates require reinstalling the runtime and reloading the idle shared worker.

This lock controls application processes on this machine. It cannot stop a human
or unrelated automation from opening the same account in another browser or on
another device. Such access must be coordinated by routing agent research through
this broker. Remote clients must connect to the central worker host, rather than
create a second provider installation for the same account. No public HTTP
listener, provider credentials or browser cookies are exposed through MCP.

An owner-approved temporary allowance can set `dailyLimit` up to150 locally,
`temporaryAllowanceDay` to one UTC date and `allowedProjects` to the approved
project IDs. The worker checks the date and project before reserving an attempt
and again at actual report dispatch. Outside that day collection stays paused;
the ledger is never reset. Configuration is cached by the worker, so apply changes
only with a controlled idle-worker reload. This is an application allowance and
does not assert or modify a vendor quota. Keep the existing dispatch spacing.
