# Shepherd-Core - Config-Models

:::{note}
TODO: WORK IN PROGRESS
:::

The models offer

- one unified interface for all tools
- auto-completion with neutral / sensible values
- complex and custom datatypes (i.e. PositiveInt, lists-checks on length)
- checking of inputs (validation) and type-casting
- generate their own schema (for web-forms)
- recursive inheritance (for content-configs)
- pre-validation
- store to & load from yaml or json with typecheck through wrapper
- included documentation

## Experiment

This category includes configuration-models for setting up an experiment. Part of the sub-systems are in the next section [](#observer-capabilities).

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.Experiment
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.TargetConfig
```

## Observer Capabilities

These are some of the sub-systems for configuring [experiments](#experiment) and also [tasks](#tasks).

[Link to Source](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/experiment)

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.PowerTracing
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.GpioTracing
```

```text
deactiveated due to Error (TODO)
.. autopydantic_model:: shepherd_core.data_models.experiment.GpioActuation
.. autopydantic_model:: shepherd_core.data_models.experiment.GpioLevel
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.SystemLogging
```

## Content-Types

Reusable user-defined meta-data for fw, h5 and vsrc-definitions.

[Link to Source](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/content)

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.EnergyEnvironment
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.Firmware
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.VirtualHarvesterConfig
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.VirtualSourceConfig
```

## Tasks

These are digestible configs for shepherd-herd or -sheep.

[Link to Source](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/experiment)

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.HarvestTask
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.EmulationTask
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.FirmwareModTask
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.ProgrammingTask
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.ObserverTasks
```

```text {eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.TestbedTasks
```
