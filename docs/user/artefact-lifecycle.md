For each artefact type we need a plan for how to handle the artefact lifecycle.

Initialization:
 - How are the artefacts created in a new project -> does this differ if the project is brand new or existing?

Creating Artefacts:
 - How are new artefacts created? What is the trigger? Is it deterministic or agent triggered?
 - If artefacts are created by the agent, does there need to be a backup process where the agent forgets to create one.
 - If an agent searches for a concept or convention that doesn't exist, should we trigger the creation of a new artefact?

Maintaining Artefacts:
 - How are artefacts maintained? appending is safe but the artefact could become cluttered. Replacing content can be destructive. Under what conditions does it make sense to maintain an artefact? Adding comments to concepts and conventions could be a good solution - we could then have a maintainer-agent that assesses the quality of the comment and decides if it should be incorporated into the artefact. Comments could have votes similar to Stack posts.

Deprecating Artefacts:
 - How and when are the artefacts deprecated? Staleness, removal of source code, etc.
 - Should we deprecate them or remove them entirely?
 - Will this be triggered by the coding agent, maintainer-agent or automated?

Reading and Using Artefacts:
 - How artefacts are read and used by the agent. Hooks? Commands? Sub-agents? This is arguably the most important part of the artefact lifecycle, if the agent doesn't know about the artefacts it can't use them.