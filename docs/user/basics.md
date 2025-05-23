# Basics

**Shepherd** is a testbed for battery-less cyber-physical systems, also publicly labeled as Internet of Things.
It allows to record harvesting conditions at multiple points in space over time.
The recorded data can be replayed to attached wireless sensor nodes (targets), examining their behavior under the constraints of spatio-temporal energy availability.

For a detailed, but slightly outdated description see our [Paper](https://wwwpub.zih.tu-dresden.de/~mzimmerl/pubs/geissdoerfer19shepherd.pdf) for shepherd version 1. Currently, version 2 is in use, which adds many improvements, while keeping the underlying idea.

A **shepherd** instance consists of a group of spatially distributed **shepherd** observers that are time-synchronized with each other.
Each **shepherd** observer consists of a single-board computer (SBC), the **shepherd** cape and a particular choice of connected targets.

Shepherd works in two key modes: [](#harvester) and [](#emulator).


## Time-synchronization

Generally, shepherd can be used on a single observer or without time-synchronization, for example, to measure the amount of energy that can be harvested in a particular scenario.
The more interesting feature however is that it enables to explore harvesting conditions across time and space, which is a crucial step towards collaboration and coordination of battery-less nodes.

For tethered settings, we propose to use the [Precision Time Protocol (PTP)](https://en.wikipedia.org/wiki/Precision_Time_Protocol).
It requires that all shepherd nodes are connected to a common Ethernet network with as little switching jitter as possible.
The BeagleBone has hardware support for PTP and Linux provides the necessary tools.

In mobile or long-range scenarios, it might not be feasible to connect the observer with Ethernet.
Instead, you can use the timing signal (PPS) from a GPS receiver.
We have designed a GPS capelet (hardware/capelet_gps) to easily connect a GPS receiver and provide all necessary software in our repository.

## Harvester

For recording a harvesting scenario, shepherd observers can be equipped with a harvesting transducer, e.g. a solar panel or piezo-electric harvester.
This transducer is connected to the input of the harvesting circuit on the shepherd cape.
The circuit is a software-controlled and -monitored current-sink with a variable voltage.

By generalizing the approach of shepherd v1 with a dedicated harvest-IC the circuit became more flexible.
The software currently supports to switch between constant voltage (CV) harvesting and maximum power point trackers ([MPPT](https://en.wikipedia.org/wiki/Maximum_Power_Point_Tracking)), with
an open circuit voltage (VOC) or perturb & observe (PO) algorithm.
The implementation is parametrized and can therefore be altered on the fly, e.g. to mimic a BQ25505-Converter by scheduling the 256 ms long VOC measurement every 16 s.

A second advantage of the circuit is that it allows to capture the character of the harvesting transducer as well as the energy scenario.
A harvesting transducer is characterized by its IV-curve, determining the magnitude of current at a specific load voltage.
By capturing a continuous stream of curves the energy scenario is recorded as well.
This abstraction decouples the harvesting from the recording-process and postpones it. The harvesting-algorithm can therefore become part of the emulation-process.

A group of shepherd observers can be deployed to the environment of interest to measure the energy that can be harvested at each node.
The time-synchronization allows to gather the readings from multiple observers with respect to a common time-line.
The data thus represents the spatio-temporal energy availability.

## Emulator

In emulator mode, spatio-temporal current and voltage data is replayed to a group of sensor nodes (targets).
Each shepherd observer hosts a current source that can precisely supply the target ports and regulate in real-time.
Relying on time-synchronization, shepherd can thus faithfully reproduce previously recorded (or model-based) spatio-temporal energy conditions.

The user has the option of adding virtual power-supply parts between the energy-recording (input) and the target port (output), see [](./virtual_source).
This approach can be seen as a hardware-in-the-loop simulation ([HIL](https://en.wikipedia.org/wiki/Hardware-in-the-loop_simulation)) that - similar to the harvester - is fully parametrized.

```{figure} media/virtual_source_schemdraw.png
:name: vsource_schem

fully customizable power supply toolchain
```

The calculations are energy-based and happen in real-time. As default the components behave neutral, so the pictured diodes and resistors have a voltage drop of 0 V, and the central intermediate storage capacitor has no capacity.
This allows to define presets by specifying a minimal parameter-set. Some directly usable presets are:

- direct / neutral
- diode + capacitor
- diode + resistor + capacitor
- BQ25504 (boost only)
- BQ25570 (boost + buck)
- BQ-Converter with an immediate (schmitt-) trigger for power-good-signal (common modification)

In case of recorded IV-Curves there is also the option of specifying the harvest-algorithm.
The parameters will be explained in depth in the chapter [](./virtual_source_old.rst).

Like other testbeds, shepherd records the targets power draw (voltage and current) during emulation.
Furthermore, nine GPIO lines (including bidirectional UART) are level-translated between shepherd and the attached target.
This allows to record and trace the target-behavior.

## Remote programming/debugging

Both target-ports feature four programming lines. These can either be used for two separate SWD- and SBW-connections or in theory for one JTAG-connection to program a variety of MCUs. Shepherds current [nRF52-Target with FRAM](https://github.com/nes-lab/shepherd-targets) makes use of that flexibility by pairing the nRF52 with the MSP430FR.

For convenient debugging and development, shepherd implements a fully functional Serial-Wire-Debug (SWD) debugger, leveraging the power of [OpenOCD](https://openocd.org/).
SWD is supported by most recent ARM Cortex-M and allows flashing images and debugging the execution of code.
Older platforms typically provide a serial bootloader, which can be used to flash images over the pre-mentioned UART connection. The same approach should work for JTAG.

```{note}
The openOCD-method was officially deprecated and deactivated, but with a bit of tinkering it can be installed and used.
```
