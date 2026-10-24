# Documentation

Text Style Transfer derives a writing style from own text samples, makes it adjustable through style
sliders and measured targets, and exports it as an Agent Skill. The same settings rewrite texts within
the application. The chapter [Workflows](workflows.md) describes the main task step by step.

| Chapter | Content |
|---|---|
| [Workflows](workflows.md) | common tasks as sequences of steps, including the creation of a skill from an own text |
| [Functional description](functional.md) | the functions of the six tabs |
| [Installation](installation.md) | requirements, installation with pip or Docker |
| [Configuration](configuration.md) | every environment variable |
| [Architecture](architecture.md) | modules, data flow, invariants |
| [Changes to the system](system-impact.md) | what the application writes or changes, and how to undo it |
| [Operation](operations.md) | recurring tasks with commands to verify them |
| [Glossary](glossary.md) | terms used in the interface and in this documentation |

The design notes give the reasons for decisions that cannot be read from the code:

- [Two paths: neutral intermediate text or direct](design/two-paths.md)
- [Languages: interface and text](design/languages.md)
- [Profile format and profile code](design/profile-format.md)
- [Privacy defaults and sessions](design/privacy.md)
- [Export as a skill](design/skill-export.md)
