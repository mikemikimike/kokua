# Tool access

An agent is a model plus the tools it may call, and "which tools" turns out to be three separate
questions that most early agent code answers with one list. Kokua names them apart, gives each its own
key in `config.toml`, and this page explains why they are separate, what each one does, and how the
same three questions show up in other frameworks under other names.

| Axis | The question | Key |
| --- | --- | --- |
| **Availability** | What can this agent ever call? | `available` |
| **Residency** | What is in its context from the start? | not built yet; see [below](#residency-what-exists-today) |
| **Approval** | What asks before it runs, and who answers? | `confirm`, `review` |

Every key lives in one subtable per agent, `[agents.<name>.tools]`, with `[assistant.tools]` as the
default for the approval half. The whole reference is
[`[agents.<name>.tools]`](../reference/configuration.md#agentsnametools); this page is the argument.

```toml
[assistant.tools]
confirm = ["skills.add_skill_script", "mcp.add_mcp_server", "config.update_config"]  # asks you
review = ["compute.run_command", "compute.execute_python", "fs_write"]              # asks a reviewer, then you

[agents.researcher.tools]
available = ["web", "misc", "time", "messaging"]   # inherits [assistant.tools]'s confirm and review
```

## Availability: fixed by the host, never by the model

`available` is the list of toolsets an agent can call, and nothing else: no code path adds a tool to an
agent that did not name it. That is the corollary to
[principle 2](design-principles.md#corollary-a-capability-is-declared-never-defaulted) in the
terms of this page, and it is the same everywhere the field has looked.

- Anthropic's Messages API fixes the capability in the request's `tools` array. Its tool search can
  hide a tool's definition until needed (`defer_loading`), but only for tools already in that array;
  the model finds a tool, it does not acquire one.
- The OpenAI Agents SDK's `tool_filter` narrows what a configured MCP server may offer an agent.
- Claude Code gives a subagent a `tools` list in its definition, and its permission rules are written
  by the user in settings, not by the model.
- Hermes children inherit their parent's toolsets, and the model cannot name others.
- OpenClaw enforces per-agent `tools.allow` and `tools.deny`, revalidated on the host side.
- `langgraph-bigtool` retrieves from a registry the host built.

No surveyed framework lets the model grant itself a capability the host did not, and Kokua's list is
the same idea with a name. (Those descriptions are as each project documented itself in October 2026;
treat them as pointers, not as their current state.)

**Why it fails closed.** An agent holds exactly the toolsets named, so a toolset added later reaches
nobody until a person writes its name in a list. The alternative, "everything is available unless
excluded", fails open on growth: a new plugin, a new Kokua toolset, or a skill the assistant wrote would
reach every agent, the researcher included, with nothing to notice the omission. The worked example is
AIMU 0.31.0, when the `fs` group gained `write_file` and `edit_file`. Had availability been "whatever
`fs` holds", an upgrade alone would have given every agent declaring `fs` a capability nothing
declared. Kokua instead split the group by reach into two toolsets, `fs` (reads) and `fs_write`
(writes), so "read a file and do not write one" is something an agent's list can say. The shipped
`introspector` holds `fs` for exactly that reason.

One name inside the approval lists, `core`, is reserved for the two tools no toolset provides
(`spawn_subagent` and `activate_skill`), and a delegating agent earns `spawn_subagent` by naming
workers in `delegates_to` rather than by `available`.

## Residency: what exists today

Residency asks a different question from availability: of what an agent *could* call, how much sits in
its context window on every request? Every other surveyed framework treats this as the dynamic axis.
Anthropic's tool search, Claude Code's deferred tools, Hermes' tool search, and `langgraph-bigtool`'s
embedding retrieval are one pattern: a cheap index stays resident, and a tool's full schema is loaded
when it is wanted. Agent Skills' progressive disclosure is the same idea applied to instructions.

Kokua does not have this yet. **Today every available toolset is resident**: an agent's `available`
list is also exactly the tools in its context on every call, and `kokua agents` says so. The
`"all"` value for `available` and deferred loading are designed and not built. They are named here
because the axis is real and because the cost is visible in the meantime: each model call in the web
UI shows its `N tools` count, which is residency as the model experienced it. When the axis arrives it
gets its own key, and this page grows a section.

## Approval: a per-call layer

Availability decides whether a call can happen at all. Approval decides, for a call that can, whether
it asks first. Kokua has two buckets beyond "just runs":

- **`confirm`** asks you.
- **`review`** asks a model reviewer first, and asks you if the reviewer does not approve. See
  [Auto-approval](auto-approval.md) for what that reviewer is and is not.

A tool in neither list runs. Entries use one vocabulary, the one `available` uses: `<toolset>` (or
`<toolset>.*`) for a whole capability, `<toolset>.<tool>` for one tool, `core.<tool>` for the reserved
two. The shipped default names `fs_write` bare so a writer AIMU adds to that group later is gated on
arrival, and names `compute.execute_python` explicitly because `compute` also holds `calculate`.

This is the layer other frameworks call permissions or authorization policy. Managed Agents has three
policies, `always_allow`, `always_ask`, and `auto`; OpenClaw's approval engine says allow, deny, or ask;
Claude Code has permission rules plus an auto mode. Kokua says "approval" because the code already did
(`HumanGate.approve`, AIMU's `tool_approval`, the approval card), and because "authorization" is already
taken in this codebase by MCP's OAuth flow.

Note what is missing: there is no deny bucket in the approval lists. A tool an agent must never call
belongs outside its `available` list, which is stronger than a refusal, since the tool does not exist
for that agent. And the reviewer in `review` cannot deny either, which is the whole of the claim in
[Auto-approval](auto-approval.md#the-security-claim-in-one-sentence), and a deliberate contrast with
Managed Agents' `auto`, where the model's verdict stands.

### The pair is inherited whole

`confirm` and `review` are one policy written as two lists, so they are declared or inherited together.
An agent whose `[agents.<name>.tools]` table declares neither inherits `[assistant.tools]`'s pair. An agent that
declares either one declares its whole policy, and a key it leaves out is empty:

```toml
[agents.coder.tools]
available = ["compute", "fs_write", "time"]
confirm = ["fs_write"]        # review is now empty, not inherited
```

The reason is that inheriting each key independently lets an inherited `review` entry overlap a declared
`confirm` entry, and neither "the declared one wins" nor "merge them" is something a reader could
predict. Taking the pair whole costs one foot-gun: writing `confirm = ["fs_write"]` to add a gate also
drops the default's other entries, because a declared policy *replaces* the default and never merges. It
has to replace, because [principle 6](design-principles.md#6-security-is-explicit-and-user-controlled)
allows loosening a control as well as tightening it. Rather than change the rule, Kokua shows you the
result: `kokua agents` prints each agent's resolved lists and where they came from, and a line per
agent goes to stderr at startup.

### Each agent's gate is bound to that agent

A gate entry is a tool name, and the policy that matters is the one belonging to whoever is making the
call. Kokua resolves one policy per agent after every agent is wired (a tool name exists only once its
toolset has been built), and binds the human gate to the agent's name. The entry agent's gate is its own.
A delegated worker's gate rides in its spawn spec's `"tool_approval"` key (AIMU 0.37.0), bound to that
worker's name, so a `coder` that declares `confirm = ["fs_write"]` is held to that and a `researcher`
inheriting the default is held to the default.

A composed worker (`compose_subagent`, which builds one for a single task) is not an agent the config
describes, so it is gated as `composed:<label>` and always gets the default tier. That is the safe
direction: a worker built from the whole registry for one call is never *less* governed than the
default, and no table has to exist for it. It is also why `:` and `[` are reserved in agent names; they
are how the gate tells a declared agent from a composed one and from the default tier's own label.

The approval prompt says which agent is asking ("Allow coder to run ..."), because with several agents
holding different policies, a bare tool name no longer tells you whose call you are approving.

### What startup checks

A gate that holds nothing back is the one mistake whose symptom is the absence of a symptom, so each of
these fails startup rather than warning:

- an entry matching no tool, or naming a toolset the agent does not list in `available`;
- a tool listed in both `confirm` and `review` of one policy;
- `[security.auto_approval]` enabled with no `review` entry anywhere, or a `review` entry naming a tool
  in `[security].never_auto_approve`, the floor beneath the reviewer. That second check only runs when
  auto-approval is enabled.

With auto-approval off, `review` entries prompt you exactly as `confirm` ones do: turning it off never
ungates a call. Unattended turns still auto-deny every gated call, whichever list holds it.

## Where the old keys went

Before this split, one list per agent (`[agents.<name>].tools`) and two global lists
(`[security].confirm_tools` and `[security.auto_approval].tools`) carried all three questions at once.
Those keys now fail startup with a message naming their replacement; there is no migration code. The
table is in the [configuration reference](../reference/configuration.md#removed-keys).

## See also

- [Configuration reference](../reference/configuration.md#agentsnametools): every key, the pair rule, and
  the removed keys.
- [Auto-approval](auto-approval.md): the `review` bucket in full, and how other assistants build it.
- [Design principles](design-principles.md): principles 2 and 6, which this page is the long form of.
- [Architecture](architecture.md#how-an-agents-tools-resolve): where each axis is resolved in code.
- [`core/approval.py`](https://github.com/saxman/kokua/blob/main/src/kokua/core/approval.py): the module
  that resolves each agent's policy.
