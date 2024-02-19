# Virtual Source

While Shepherd v1 was built around an actual harvesting-IC the new version virtualizes most parts like the harvester, storage capacitors and voltage converters.
By switching to a software defined system the sourcing of energy becomes fully configurable.
The simulation loop runs in real-time with 100 kHz and allows to emulate a wide variety of voltage converter circuits.

:::{note}
WORK IN PROGRESS
:::

## Harvester

With one of the latest additions of sampling [IV-curves](https://en.wikipedia.org/wiki/Current%E2%80%93voltage_characteristic) during harvest, it is now possible to also emulate the actual harvesting. The harvesting options are

- constant voltage (CV)
- maximum power point tracking (MPPT) based on
  - open circuit voltage (MPPT_VOC), or
  - perturb & observe (MPPT_PO)

As an

```yaml
- datatype: VirtualHarvesterConfig
  parameters:
    id: 1040
    name: mppt_voc
    description: MPPT based on open circuit voltage for solar
    inherit_from: neutral
    algorithm: mppt_voc
    setpoint_n: 0.76
    interval_ms: 100     # between measurements
    duration_ms: 1.2     # solar can overshoot when load is removed
    current_limit_uA: 5  # boundary for detecting open circuit in emulated version (working on IV-Curves)
```

### References

- [VirtualHarvesterConfig in corelib](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_harvester.py)
- [Harvester-Fixtures in corelib](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_harvester_fixture.yaml)
- https://github.com/orgua/shepherd/blob/main/software/firmware/pru0-shepherd-fw/virtual_harvester.c

## Emulator

```{figure} media/virtual_source_schemdraw.png
:name: vsource

fully customizable power supply toolchain
```

```yaml
- datatype: VirtualSourceConfig
  parameters:
    id: 1011
    name: diode+capacitor
    description: Simple Converter based on diode and buffer capacitor
    inherit_from: neutral
    V_input_drop_mV: 300  # simulate input-diode
    C_intermediate_uF: 10  # primary storage-Cap
```

### References

- [VirtualSourceConfig in corelib](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_source.py)
- [Source-Fixtures in corelib](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_source_fixture.yaml)
- [VirtualSource-Model in pru](https://github.com/orgua/shepherd/blob/main/software/firmware/pru0-shepherd-fw/virtual_converter.c)
- [VirtualSource-Model in corelib](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/shepherd_core/vsource)
- [example of a VirtualSource-Simulation](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/examples/vsource_simulation.py)
