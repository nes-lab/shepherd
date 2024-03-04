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

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.Experiment
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.TargetConfig
```

## Observer Capabilities

These are some of the sub-systems for configuring [experiments](#experiment) and also [tasks](#tasks).

[Link to Source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/experiment)

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.PowerTracing
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.GpioTracing
```

```
deactiveated due to Error (TODO)
.. autopydantic_model:: shepherd_core.data_models.experiment.GpioActuation
.. autopydantic_model:: shepherd_core.data_models.experiment.GpioLevel
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.experiment.SystemLogging
```

## Content-Types

Reusable user-defined meta-data for fw, h5 and vsrc-definitions.

[Link to Source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content)

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.EnergyEnvironment
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.Firmware
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.VirtualHarvesterConfig
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.content.VirtualSourceConfig
```

## Tasks

These are digestible configs for shepherd-herd or -sheep.

[Link to Source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/experiment)

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.HarvestTask
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.EmulationTask
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.FirmwareModTask
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.ProgrammingTask
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.ObserverTasks
```

```{eval-rst}
.. autopydantic_model:: shepherd_core.data_models.task.TestbedTasks
```
