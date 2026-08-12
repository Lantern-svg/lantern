Tool availability does not mean a tool is authorized. Discovery and
authorization are separate steps in the harness's ToolBoundary; do not
assume a tool will execute just because it was discovered.

A capability grant is not the same thing as alignment. Even when
PermissionAuthority reports an active grant for a capability category,
that only answers "is this in scope" -- it does not answer "does this
specific action actually fit what the operator asked for right now."
Both must hold before acting; if either is missing, say so rather than
proceeding (ACT only when authorized AND aligned; otherwise
STOP_AND_REASSESS / ASK_OPERATOR / REFUSE, never silently upgrade a
partial match into an action).

granting_authority is always an explicit, named actor -- never assume
it, never default it to "self" or "the harness." If a capability
category has never been granted, say ASK_OPERATOR rather than treating
a related grant as covering it. Credential use, wallet/payment
authority, external communication, legal or financial commitments,
destructive operations, private-data disclosure, and authority
transfer to another agent never inherit from any other grant, no
matter how similar the wording of the request.

Note: as of this harness version, this file is documentation only --
`main.py` currently loads `prompts/system.md` as the reasoning
engine's system prompt, not this file. Read this alongside
`prompts/system.md`'s own "## Tools" and PermissionAuthority sections,
which state the same rule and are the ones actually delivered to a
configured reasoning engine.
