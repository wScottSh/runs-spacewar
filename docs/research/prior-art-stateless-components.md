# Prior art: stateless components wired by the net

Issue #46, part of #45. The question: in systems where a component names no state and the net says what each use reads and writes, how is that binding written? For each system below: where the binding lives, how one component is reused at many sites, how nesting works, and what carries over to a RUNS Network that may only fire, guard and loop, with `runsc` unchanged.

Every quotation comes from the primary source linked in its section. Inferences are marked as inferences.

## Findings in brief

1. **Every system surveyed has the component name its own formal ports.** No system has a component that names nothing. FBP components name ports such as `IN` and `OUT`. CPN modules have port places. Unix programs use file descriptors 0, 1 and 2. A LabVIEW subVI assigns its own controls to connector-pane terminals. Lucid functions have formal parameters. The net or graph binds these local names to the places of the caller, one use at a time. For RUNS, "a Processor names no Records" therefore most plausibly means "a Processor names only its own port Records, and the Network binds them at each use".
2. **The binding is written in one of three ways.** (a) As a connection list at the use site: FBP `CONNECT`, CPN port assignment, LabVIEW wires, Unix `|` `<` `>`. (b) As an equivalence, where port and socket are one place seen twice: FBP's `=>` and CPN's port/socket "compound place". (c) As a copy through a buffer: FBP connections and Unix pipes. RUNS today can write only (c), as copy Processors around a fixed port Record. Spacewar's `sine_call` and `multiply_call` already do this.
3. **Nesting is flattened before execution in every system that defines it.** DFDM networks "can be built up hierarchically, but are flat at run-time". CPN Tools instantiates modules "prior to simulation". Simulink's virtual subsystems "are neither conditionally nor atomically executed". This matches #45's "collapsed it is `run name`, expanded it is its lines".
4. **Reuse with internal state forces one instance per site.** Examples: CPN module instances ("each instance of a module has its own marking"), LabVIEW preallocated clones, FBP processes ("each process must have its own set of working storage") and Lucid function invocations (coroutines with their own running sums). RUNS Processors hold no state, so one file serves every site with no instances. A sub-Network that keeps per-site state must keep it in Records the Network binds, or in a slot of a collection.
5. **CPN names a second route to reuse: folding sites into a token component.** That is RUNS's `run p(slot)`. RUNS already compiles it, but it reaches only sites that differ by which slot of one collection they touch.

## Flow-based programming (J. Paul Morrison)

Sources: Morrison, [FBP Concepts](https://jpaulm.github.io/fbp/concepts.html); *Flow-Based Programming* (1994) chapters [V, Parametrization of Reusable Components](https://jpaulmorrison.com/fbp/reusparm.shtml), [VII, Composite Components](https://jpaulmorrison.com/fbp/compos.shtml), and [Notation](https://jpaulmorrison.com/fbp/notation.shtml).

- **Where the binding lives.** It lives in the network definition, outside the component. A component names its ports, and the names are local: "port names only have meaning within the components referencing them (and at the network level, of course)." A diagram "can be converted directly into a list of connections", for example `CONNECT A.X,(2,C)`.
- **Reuse at many sites.** "The concept of ports is what allows the same component to be used at more than one place in the network." Several processes can run one component: "It is permitted for processes B and C to be executing the same code, so each process must have its own set of working storage." Per-site constants arrive as data, not as edits to the component: an Initial Information Packet (IIP) "is defined as part of the network definition, and is associated with an input port". Chapter V's argument for black-box reuse is that a component "communicates with the outside world only through data being sent to or received from its ports" and "can be held in object form, and never modified."
- **Nesting.** A subnet has "sticky" connections, arrows with an open end: `G: -> A -> 2 B ->, I -> B`. G "can be used as an ordinary filter in a network, and, like all components, can be used more than once in a network". At this level, "the network doesn't know that G even is a composite." Expansion flattens it and qualifies each copy: "you will see two instances each of I, A and B". THREADS writes the subnet boundary as `MIN => IN process_C(THVIEW)`, which identifies the subnet's port with an internal port. Morrison says the `=>` is used "to stress the fact that these are not really connections, but are more like equivalences." On run time: "DFDM networks can be built up hierarchically, but are flat at run-time."
- **What carries over.** Three things. Port names local to the component. The binding as a list kept apart from the component. A bundle flattened at build time with per-copy qualifiers. FBP binds a subnet's ports by equivalence (`=>`), not by copy. RUNS has no way to say two Record names are one Record without a language change, so the equivalence form does not carry over under #45's constraint.

## Coloured Petri nets (Jensen; Jensen, Kristensen and Wells)

Sources: Jensen, Kristensen and Wells, "[Coloured Petri Nets and CPN Tools for Modelling and Validation of Concurrent Systems](https://cs.au.dk/fileadmin/site_files/cs/research_areas/centers_and_projects/sttt2007.pdf)", *STTT* 9 (2007) 213–254 (the authors' copy, linked from [Aarhus CPN group](https://cs.au.dk/cpnets/papers/new-overview)); Jensen, [CPN lecture slides](https://users.cs.fiu.edu/~hex/CEN6075-09/PetriNets/CPN-Jensen.pdf) (2005).

- **Where the binding lives (flat nets).** In the arc inscriptions. A transition's arc expressions are "built from typed variables". A binding assigns values to the variables "that appear in the surrounding arc expressions of the transition". Which places a transition touches is fixed by its arcs in the net, not by the transition. But a flat transition appears only once, so flat nets have no reuse.
- **Where the binding lives (hierarchy).** At the substitution transition. A module has port places tagged input, output or input/output, plus internal places. The places around a substitution transition are its sockets. A **port assignment** "maps the port places of the submodule to the socket places of the substitution transition". "Each port has the same name as the socket to which it is assigned, but this is not required." The binding is an equivalence: "When a port is assigned to a socket, the two places constitute two different views of a single place ... they always have the same marking."
- **Reuse at many sites.** One module serves several substitution transitions, each with its own port assignment. The Transmit module serves TransmitData (IN→A, OUT→B) and TransmitAck (IN→C, OUT→D). Reuse makes instances: "Each instance of a module has its own marking." Instances are fixed before execution: "instantiation of modules is done prior to simulation ... it is not possible to dynamically instantiate new modules during the simulation." The slides cite a model with "43 modules with more than 100 instances."
- **The folding alternative.** Instead of one module instance per receiver, "multiple receivers may also be modelled by adding a new component to the token colours" (slides, "Another solution"). One copy of the net then carries an index in its tokens.
- **Nesting.** Substitution transitions nest to any depth ("CPN models of larger systems typically have up to 10 abstraction levels"). A substitution transition does not fire on its own: "substitution transitions do not have guards, and arcs connected to substitution transitions do not have arc expressions ... the substitution transition represents the compound behaviour of its submodule." CPN Tools edits the hierarchy both ways. It has "Move a transition or group to a new submodule" and "Replace a substitution transition with its submodule", which are collapse and expand. Fusion sets are a second, global channel: they "allow a number of places ... to be glued together into one compound place across the hierarchical structure."
- **What carries over.** This is the closest match to RUNS, since a RUNS Network is already Petri-net-like.
  - A sub-Network is a module.
  - `run name` is a substitution transition, with no guard of its own; the guard sits on the enclosing `if`.
  - The port assignment is the binding #45 asks for.
  - `run p(slot)` is the folding alternative: one net, with the site as a token component.
  - A module's internal places become per-instance state. RUNS Processors hold none, so only Records can carry it.
  - Under #45's constraint, the equivalence form of the port assignment has no RUNS spelling. A port can be bound only by copy Processors, or by every site sharing one port Record, as a fusion set does.

## Unix pipes and file descriptors (Ritchie and Thompson)

Sources: Ritchie and Thompson, "[The UNIX Time-Sharing System](https://homepages.uc.edu/~thomam/Intro_Unix_Text/Misc/cacm.html)", *CACM* 17:7 (1974); Ritchie, "[The Evolution of the Unix Time-sharing System](https://pdos.csail.mit.edu/6.828/2009/readings/ritchie79evolution.html)" (1979).

- **Where the binding lives.** In the shell command line, and never in the program. The paper says of the file name after `<` or `>`: "in fact it is interpreted completely by the shell and is not passed to the command at all. Thus no special coding to handle I/O redirection is needed within each command; the command need merely use the standard file descriptors 0 and 1 where appropriate." The ports are positional (0, 1, 2) and fixed by convention. A pipe carries a copy: "the standard output of each command [is] delivered to the standard input of the next command". "Neither process need know that a pipe, rather than an ordinary file, is involved."
- **Reuse at many sites.** Any program that reads 0 and writes 1 can sit anywhere in any pipeline. Ritchie on why this beat Multics' spliceable I/O modules, which "required that the modules be specially coded in such a way that they could be used for no other purpose": "The genius of the Unix pipeline is precisely that it is constructed from the very same commands used constantly in simplex fashion." Commands were changed to fit: "no one had imagined that anyone would want the sort or pr utility to sort or print its standard input if given no explicit arguments."
- **Nesting.** A shell script is itself a command with fds 0, 1 and 2, so it can sit in a pipeline. The notation is limited. Ritchie calls it "unabashedly linear", and asks "what is the best way to compare the outputs of two programs?"
- **What carries over.** Fixed, conventional port names inside the component (fd 0/1/2, or a Processor's own `*_call` Record), bound by the caller. Also the lesson that reuse came from a convention every program obeys, not from a mechanism. Inference: in RUNS the matching convention would be one fixed shape of port Record per Processor family, used by every site.

## Lucid (Ashcroft and Wadge)

Source: Ashcroft and Wadge, "[Structured Lucid](https://wrap.warwick.ac.uk/47206)", Warwick Theory of Computation Report 33 (rev. 1980). The scanned PDF's text layer is noisy OCR. The quotations below are read from that layer with obvious OCR errors corrected, and have not been checked against the page images.

- **Where the binding lives.** At the application. A function definition has formal parameters, and the report states USWIM's restriction that "the formal parameters of a function definition be individual variables". A defined function may also use **globals**, free variables bound by the enclosing scope, and "globals have the same meaning inside a phrase as outside". A function that reads a global depends on a name outside itself. That is the Lucid counterpart of a Processor that names a Record.
- **Reuse at many sites.** The report's running-average function `avg` is defined once and applied twice in the variance program, to the input stream and to the squared deviations. Operationally the report treats `avg` "as a coroutine, with two invokations", each keeping its own running sums. So reuse with history-dependent state yields one activation per site.
- **Nesting.** `valof ... end` phrases nest, with locals scoped to the phrase. The report separates subcomputations that "freeze" the enclosing environment from coroutine-like ones that run in step with it.
- **What carries over.** Parameters bound at each application keep a component free of outside names, and globals are exactly the impurity #45 removes. Lucid's reuse model is a function call with arguments, but RUNS `run` passes only a slot. Lucid therefore supports the goal without offering a spelling RUNS compiles today.

## LabVIEW subVIs (National Instruments)

Source: LabVIEW Help, as mirrored at [unofficial-lvdocs: Reentrancy](https://rajsite.github.io/unofficial-lvdocs/lvconcepts/reentrancy.html) and [Assigning Terminals to Controls and Indicators](https://rajsite.github.io/unofficial-lvdocs/lvhowto/Assigning_Controls_and_Ind.html). NI's own docs site renders only through JavaScript and could not be fetched. The mirror is a third-party copy of NI's help text, so treat these quotations as NI's wording unconfirmed against ni.com.

- **Where the binding lives.** It is split. Inside the subVI, "you can assign a front panel control or indicator to each of the connector pane terminals". These are the subVI's own formal ports. The caller binds actual values by wiring the subVI node's terminals on its own block diagram.
- **Reuse at many sites.** Each placement of the subVI on a caller's diagram is a "call site". Reuse is tied to state through reentrancy. Non-reentrant: "a single data space to store the parameters of its callers, any temporary values computed during execution, and any state that the non-reentrant VI maintains between calls." Preallocated clone: "a separate, non-shareable, clone for each use of the subVI", so it "maintains state for each call site". Shared clone "does not maintain state" predictably: "call sites may end up sharing state."
- **What carries over.** The same conclusion as CPN and FBP: once a reused piece keeps state, the system has to choose between one shared copy and one copy per site. The non-reentrant single data space corresponds to one shared `*_call` Record serving every `run sine`. That is safe in RUNS because the Network runs one line after another, so no two sites are ever active at once. This is an inference from RUNS's ordering rule, not a LabVIEW claim.

## Simulink subsystems and libraries (MathWorks)

Sources: MathWorks, [Subsystem block](https://www.mathworks.com/help/simulink/slref/subsystem.html), [Group Blocks into Subsystems](https://www.mathworks.com/help/simulink/ug/creating-subsystems.html), [Linked Blocks](https://www.mathworks.com/help/simulink/ug/creating-and-working-with-linked-blocks.html).

- **Where the binding lives.** Inside the subsystem, Inport and Outport blocks define its ports: "Placing a block such as an Inport ... in a subsystem adds an external input port to the Subsystem block." The parent diagram's lines to those ports are the binding.
- **Reuse at many sites.** Through libraries. Placing a library block creates "a referenced instance of the library block", and "the link or path allows the linked block to update when the library block is updated." That is one source and many sites, which is the DRY requirement in #45. Structural edits require disabling the link, and a broken link becomes a private copy.
- **Nesting and expand/collapse.** "Virtual subsystems are neither conditionally nor atomically executed." They organize the diagram visually. Expand is a toolstrip command that replaces the Subsystem block with its contents. The docs warn that expanding "can affect the execution order of blocks because of the changes to the block paths", because Simulink derives order from the graph. Atomic subsystems instead execute "as a single block". Inference: RUNS avoids this hazard because its order is written in the text, not derived.
- **What carries over.** A RUNS sub-Network behaves like a virtual subsystem: grouping only, flattened, so expanding or collapsing it should not change the image. Library links are a model for "identical pieces are one shared file".

## Synthesis for RUNS (#45)

The table restates the sections above. "Copy" means a value is moved; "equivalence" means two names denote one place.

| System | Ports named by | Binding written at | Binding kind | Reuse with state | Nesting at run time |
|---|---|---|---|---|---|
| FBP | component (`IN`, `OUT`) | network connection list | copy (connections); equivalence for subnets (`=>`) | process per site | flattened (DFDM) |
| CPN | module (port places) | substitution transition (port assignment) | equivalence | instance marking per site; or fold into token colour | instances fixed before simulation |
| Unix | convention (fd 0/1/2) | shell command line | copy (pipe) | process per site | script is a command |
| Lucid | function (formals) | application | argument | activation per site | phrases nest |
| LabVIEW | subVI (connector pane) | caller's wires | argument | single, shared, or per-site clone | subVI node |
| Simulink | subsystem (Inport/Outport) | parent's lines | signal | per block instance | virtual: grouping only |

RUNS today, from the Spacewar text:

- `processor multiply` reads and writes only `multiply_call`. `network sine` fires it four times, after sine_reduce, sine_x, sine_x_squared and sine_term_5 (`runs/arithmetic.runs-prim`). Each preceding Processor sets `multiply_call.entry` and `.factor`. That is fixed formal ports plus copy-in at each site, the Unix/FBP pattern, and `runsc` compiles it now.
- `steer` sets `sine_call.angle`; `run sine`; then `take_sine` copies `sine_call.result` into `heading.sine` (`runs/spaceship.runs*`). The `*_call` Record is a port shared by every call site: one data space, like a non-reentrant subVI or a CPN fusion set. `take_sine` carries the comment `# dac \sn; dzm \bx; dzm \by`, so this copy corresponds to instructions the original executes. It is not an added cost.
- `run spaceship(slot)` is CPN folding: one net, and the site is a token component.

Patterns that bind by structure without a compiler change, ranked by fit:

1. **Port Records plus copy Processors (FBP/Unix/CPN-by-copy).** Each reusable Processor reads and writes only its own `*_call`-style Record. The Network binds a site by placing a copy-in Processor before the `run` and a copy-out Processor after it. Fit: compiles today, and one file serves every site. Risk: the image is the oracle. Each copy must correspond to an instruction the original executes, as `take_sine` does. Inference, not checked: where the original passed the value in AC with no store, a copy Processor would change the image unless `runsc` already keeps that field in AC.
2. **Slot folding (CPN token colour).** Sites that differ only in which slot of one collection they touch become one Processor run with `slot`. It compiles today. It does not reach sites that touch different Records.
3. **Bundles as flattened sub-Networks (DFDM, CPN substitution, Simulink virtual).** `network name` with its ports as named Records, `run name` at each site. Collapsing or expanding does not change execution, provided the bundle has no guard of its own (CPN: substitution transitions have no guards).
4. **Equivalence binding (FBP `=>`, CPN port assignment).** A site says "port `x` of this Processor *is* Record `r`", with no copy. This is the literal reading of "the Network binds Records to a Processor". No surveyed system does it without language support, and RUNS has none today. Under #45's no-compiler-change rule it is out of scope. If a site cannot be written with patterns 1–3, the CLAUDE.md rule applies: stop and report the shapes tried.

## Open points

- Whether pattern 1's copies always match the original's instructions has not been checked unit by unit. A trial split that compiles to `MATCH` (or not) would settle it.
- Not surveyed from primary sources: Kahn process networks (1974), Hoare's CSP renaming and process labelling, and VHDL `port map`. No freely fetchable primary text was found in this pass.
