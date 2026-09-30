"""krot-collect: what crawled a project's sites, read from nginx's logs, night by night.

Runs on the machine from timers, one unit per project and job, and writes into the
`krot_collect` schema of the project's own database. Every rule it follows was
paid for first by an earlier PHP implementation — see openspec change
collect-crawler-visits, design.md, for where each one comes from.
"""
