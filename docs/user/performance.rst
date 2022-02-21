Performance Specification
=========================

The `Performance specification`_ table summarizes shepherd's key performance metrics.
Refer to our paper for a detailed description of how these values were obtained.
Some of the values were measured with an early prototype and may not accurately reflect the current hardware revision.


.. table:: Performance specification

    +----------------------------+------------------------+----------------------+
    | Range                      | Harvester voltage      | 0 mV - 4.8 V         |
    +                            +------------------------+----------------------+
    |                            | Harvester current      | 0 mA - 50 mA         |
    +                            +------------------------+----------------------+
    |                            | Emulator voltage       | 0 mV - 4.8 V         |
    +                            +------------------------+----------------------+
    |                            | Emulator current       | 0 mA - 50 mA         |
    +----------------------------+------------------------+----------------------+
    | 24h DC Accuracy            | Harvester voltage      | 19.53 uV +/- 0.01 %  |
    +                            +------------------------+----------------------+
    |                            | Harvester current      | 190 nA +/- 0.07 %    |
    +                            +------------------------+----------------------+
    |                            | Emulator voltage       | 76.3 uV +/- 0.012 %  |
    +                            +------------------------+----------------------+
    |                            | Emulator current       | 381.4 uA +/- 0.025 % |
    +----------------------------+------------------------+----------------------+
    | Bandwidth                  | All recording channels | 15 kHz               |
    +----------------------------+------------------------+----------------------+
    | Risetime                   | Emulator voltage       | 7 us                 |
    +                            +------------------------+----------------------+
    |                            | Emulator current       | 19.2 us ??           |
    +----------------------------+------------------------+----------------------+
    | Max. Burden voltage        | Harvest recorder       | 50.4 mV              |
    + TODO: still applicable?    +------------------------+----------------------+
    |                            | Load recorder          | 76.1 mV              |
    +----------------------------+------------------------+----------------------+
    | GPIO sampling speed        |                        | 580 kHz - 5 MHz      |
    +----------------------------+------------------------+----------------------+
    | Power consumption          |                        | 345 mA               |
    +----------------------------+------------------------+----------------------+
    | Max. Synchronization error |                        | < 1.0 us             |
    +----------------------------+------------------------+----------------------+
