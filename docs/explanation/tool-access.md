# Tool access

An agent is a model plus the tools it may call, and "which tools" turns out to be three separate
questions that most early agent code answers with one list. Kokua names them apart, gives each its own
key in `config.toml`, and this page explains why they are separate, what each one does, and how the
same three questions show up in other frameworks under other names.

| Axis | The question | Key |
| --- | --- | --- |
| **Availability** | What can this agent ever call? | `available` |
| **Residency** | What is in its context from the start? | `resident` |
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

[agents.assistant.tools]
available = ["memory", "documents", "skills", "config", "mcp", "scheduling", "conversations", "planning",
             "capabilities", "time", "benchmark", "messaging"]
resident = ["memory", "config", "conversations", "planning", "capabilities", "time", "messaging"]  # the rest load on demand
```

## Availability: fixed by the host, never by the model

`available` is the list of toolsets an agent can call, and nothing else: no code path adds a tool to an
agent that did not name it, with a few exceptions that are themselves entered by declaration: a
non-empty `delegates_to` earns `spawn_subagent`, the entry agent's `SkillAgent` carries the skill
catalogue and script tools whether or not it declares `skills`, and `compose_subagent` draws from the
whole registry for an agent that declares `capabilities`. That is the corollary to
[principle 2](design-principles.md#corollary-a-capability-is-declared-never-defaulted), which states
the exceptions in full, in the terms of this page, and it is the same everywhere the field has looked.

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

One name inside the approval lists, `core`, is reserved for the tools no toolset provides:
`spawn_subagent` and `activate_skill`, plus `available_tools` and `load_tools` once any agent defers a
toolset (see [Residency](#residency-what-is-in-context-and-what-loads-on-demand)). A bare `core` covers
all of them and `core.<tool>` names one. A delegating agent earns `spawn_subagent` by naming workers in
`delegates_to` rather than by `available`.

## Residency: what is in context, and what loads on demand

Residency asks a different question from availability: of what an agent *could* call, how much sits in
its context window on every request? Every other surveyed framework treats this as the dynamic axis.
Anthropic's tool search, Claude Code's deferred tools, Hermes' tool search, and `langgraph-bigtool`'s
embedding retrieval are one pattern: a cheap index stays resident, and a tool's full schema is loaded
when it is wanted. Agent Skills' progressive disclosure is the same idea applied to instructions.

Kokua's version is one key and AIMU's tool groups. **`resident` names the toolsets an agent holds from
its first turn,** and it is a subset of `available`. Whatever `available` names and `resident` does not
is *deferred*: the agent can reach it, but none of its tool schemas are in the request until the model
asks for them. Leave `resident` out and every available toolset is resident, which is how the shipped
workers are declared. A `resident` entry that `available` does not hold is a startup error, because a
resident toolset is one the agent already holds. The order you write `resident` in changes nothing:
tools are presented in `available` order either way. `kokua agents` prints each agent's resident list,
or "every available toolset" when it declares none.

Note what residency cannot do: widen anything. A deferred toolset is one the agent's own `available`
list already names, so loading it is the model choosing *when* to pay for a capability the host granted,
never acquiring one. That is the same line Anthropic's `defer_loading` draws, for the same reason.

### What the model sees

An agent with at least one deferred toolset carries two more tools, which come from AIMU rather than
from any toolset: `available_tools`, which lists every toolset the agent holds or can load, and
`load_tools(name)`, which loads one. Its system prompt gains a single line naming what it can load, and
only the names:

```text
Also available, load before use: documents, skills, mcp, scheduling, benchmark.
```

This is what `available_tools` returns for the shipped entry agent, abridged:

```text
memory [resident]: Facts about the user, remembered across conversations.
config [resident]: Read config.toml and change a runtime setting, persisted back to the file. Asks first: update_config.
...
skills [loadable]: Author skills, revise them, and attach runnable scripts to them. Asks first: add_skill_script.
mcp [loadable]: Connect and disconnect remote MCP servers at runtime. Asks first: add_mcp_server.
scheduling [loadable]: Schedule, list, edit, and cancel recurring or one-off proactive tasks.
```

The description is the toolset's own (for an MCP server, its
[`description`](../reference/configuration.md#mcpserver) key), and the `Asks first` note comes from the
agent's approval policy, so a model choosing what to load knows a tool will stop for an answer before it
plans around that tool. A deferred toolset's `guidance`, the instructions it would otherwise add to the
prompt, arrives with its tools as part of `load_tools`' result, so the prompt pays for none of it until
it is used. A load lasts for the rest of the agent's life, and nothing unloads. Loaded tools go after
everything the agent already holds, so within a conversation a request's tool list only grows, which
keeps a provider's prompt cache valid. A loaded tool whose name the agent already holds is skipped, and
the result says so.

### What a load costs: the build, paid when it happens

A resident toolset is built when the agent is wired. A deferred one is built when it is loaded, through
the same `build_tools` call, in a worker thread so the event loop keeps serving other conversations
meanwhile. So whatever building a toolset does (opening the document store, for `documents`) is paid
only by an agent that loads it.

A build that fails, fails at load. The model reads AIMU's `Could not load '<name>': <error>` as the
tool's result, you get an alert naming the toolset and the agent, and the toolset stays loadable, so a
retry after the cause is fixed works. A deferred MCP server that is not connected refuses to load,
rather than loading empty. Resident, the same server builds empty and a reconnect reaches the next
rebuild; but a load is recorded as done, so an empty one would leave the server unloadable for the rest
of the conversation even after it came back.

### What a load checks: approval, before any tool is callable

An approval entry naming a deferred toolset that no agent holds resident cannot be resolved at startup,
because a tool name exists only once its toolset has built it. So startup checks the entry's shape and
holds it as *pending*, and the build resolves it: `build_tools` reports each toolset it builds to a
hook, and the hook resolves the waiting entries before a single tool is returned. That holds whoever builds the toolset: the model's
`load_tools`, a [composed worker](architecture.md#agents-and-delegation), or a rebuilt agent restoring
what its conversation loaded (below).

An entry that still matches nothing once its toolset is built, such as `mcp.add_mcp_servr`, refuses that
build and every later one, so the toolset cannot be loaded until the entry is fixed. That is failing
closed on purpose: the alternative is a tool running ungated because its gate was misspelled. On a load,
the model reads the refusal as a `Could not load` result and you get the alert.
`[security].never_auto_approve` entries naming a deferred toolset are pending in the same way, and a
build after which some policy's `review` list reaches that floor is refused too. In the shipped config this is how
`skills.add_skill_script` and `mcp.add_mcp_server` are gated: both name toolsets the entry agent
defers, and both resolve the first time their toolset is built.

### When an agent is rebuilt, it preloads

A conversation's agent is rebuilt from the stored transcript more often than you might expect: on
restart, when switching among more than eight conversations evicts the least recently used one, and when
a conversation is truncated. The new agent preloads the toolsets the transcript's `load_tools` calls
named, in the order they were first named, instead of replaying the calls. The reason is mechanical: the
agent builder is synchronous and AIMU's load is async. The end state is the same tools, the restored
ones in their original load order, with their guidance in the prompt and the names line listing only
what is still loadable.

The cost is that a preloaded toolset is held like a resident one: `available_tools` lists it as
`resident`, not `loaded`, and the two loaders now come after its tools rather than before them. A
preload goes through the same build and the same approval hook as a load. One that fails (a refused
approval entry, an MCP server still down) is logged at WARNING rather than raised as an alert, since a
rebuild is something nobody asked for, and the toolset stays deferred and loadable so the model can try
again and read the real error. A preloaded tool whose name the agent already holds is skipped
and logged. Truncation rebuilds from the shortened transcript, so a load made in the deleted turns is not
restored.

### Workers, and the shipped split

`resident` works the same on every agent. A delegated worker that declares one gets the same two tools
and the same names line, and its loads are its own: a worker is built per spawn, so what it loads ends
with it. A composed worker has no table and so no residency; everything it is composed from is built
when it is.

The shipped entry agent keeps `memory`, `config`, `conversations`, `planning`, `capabilities`, `time`,
and `messaging` resident, the toolsets it reaches for on most turns, and loads `documents`, `skills`,
`mcp`, `scheduling`, and `benchmark` on demand. Measured as the JSON of every tool spec the model is
sent, its tool block went from 30,560 bytes for all 37 tools to 16,244 bytes for nineteen (seventeen
resident, plus the two loaders): 46.8% smaller, on every round of every turn that loads nothing. The
approval gate covers the same seven tools it did. What it costs is a round: a turn that needs a deferred
toolset spends one model call on `load_tools` before it can use it. Each model call in the web UI still
shows its `N tools` count, which is residency as the model experienced it.

`available = "all"`, every installed toolset available to load, is designed for a later stage and not
built yet; today `available` is always a list.

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
toolset has been built, which is also why an entry for a deferred toolset waits for its
[build](#what-a-load-checks-approval-before-any-tool-is-callable)), and binds the human gate to the
agent's name. The entry agent's gate is its own.
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

An entry naming a toolset the agent defers is the one exception to "at startup": startup checks its
shape, and the build checks the rest, refusing the toolset rather than letting it load ungated (see
[What a load checks](#what-a-load-checks-approval-before-any-tool-is-callable)).

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
