# Virtual Source

While Shepherd v1 was built around an actual harvesting-IC the new version virtualizes most parts like the harvester, storage capacitors and voltage converters.
By switching to a software defined system the sourcing of energy becomes fully configurable.
The simulation loop runs in real-time with 100 kHz and allows to emulate a wide variety of voltage converter circuits.

:::{note}
TODO: WORK IN PROGRESS
:::

## Harvester

With one of the latest additions of sampling [IV-curves](https://en.wikipedia.org/wiki/Current%E2%80%93voltage_characteristic) during harvest, it is now possible to also emulate the actual harvesting. The harvesting options are

- constant voltage (CV)
- maximum power point tracking (MPPT) based on
  - open circuit voltage (MPPT_VOC), or
  - perturb & observe (MPPT_PO)

As an actual YAML-Example:

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
- [VirtualHarvester-Model in PRU](https://github.com/orgua/shepherd/blob/main/software/firmware/pru0-shepherd-fw/virtual_harvester.c)

## Emulator

```{figure} media/virtual_source_schemdraw.png
:name: vsource

fully customizable power supply toolchain
```

As an actual YAML-Example describing a simple diode & capacitor circuit:

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

## Sim-Example 1

Setup:

- TI BQ25504 (with default slow pwr-good & fast schmitt-trigger)
- I_inp = 100 uA @ 1200 mV
- I_out = 1 mA (active MCU), 200 nA (sleep)
- V_power_good = 2.2 V

The only difference between the two runs is the altered power-good-circuit. The original BQ25504 is too slow to inform the MCU about the low energy level and therefore the MCU drains the capacitor. Note the small voltage drop in the first picture. The BQ disconnects the output for very low voltages and reconnects it on a certain voltage. The drop is caused by the simulated output-capacity.

```{figure} media/vsource_sim_BQ25504_1200mV_5000ms.png
:name: vsource_sim_bq

BQ25504 with default slow pwr-good
```

```{figure} media/vsource_sim_BQ25504s_1200mV_5000ms.png
:name: vsource_sim_bqs

BQ25504 with fast schmitt-trigger
```

[Source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/examples/vsource_simulation.py)

## Sim-Example 2

Setup:

- diode + cap circuit with immediate schmitt-trigger for power-good
- I_inp = 100 uA @ 1200 mV
- I_out = 1 mA (active MCU), 200 nA (sleep)
- V_power_good = 2.2 V

The input-voltage is too small to charge the circuit up to V_power_good, so the capacitor is slowly discharging from its own leakage and the MCUs current-draw during sleep.

```{figure} media/vsource_sim_diode+capacitor_1200mV_500ms.png
:name: vsource_sim_diode_cap

diode + cap circuit with fast schmitt-trigger for power-good
```

[Source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/examples/vsource_simulation.py)

### References

- [VirtualSourceConfig in corelib](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_source.py)
- [Source-Fixtures in corelib](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_source_fixture.yaml)
- [VirtualSource-Model in PRU](https://github.com/orgua/shepherd/blob/main/software/firmware/pru0-shepherd-fw/virtual_converter.c)
- [VirtualSource-Model in corelib](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/shepherd_core/vsource)
- [example of a VirtualSource-Simulation](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/examples/vsource_simulation.py)
