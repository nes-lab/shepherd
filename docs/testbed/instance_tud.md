# Instance at TU Dresden

In the second half of 2023 a public instance of the Shepherd Testbed went live. This section of the documentation is the landing-page and informs users about the first steps.

## Deployment

The initial deployment is covering the ring of offices around the buildings ventilation system. The inner structure mostly blocks RF due to lots of metal vents. 14 shepherd observers are used for the testrun.

Below is a screenshot of the [Campus-Navigator](https://navigator.tu-dresden.de/etplan/bar/02) with marked node-positions.

![cfaed floor with marked node-positions](./media/cfaed_floorplan_mod.png)

Most horizontal walls are concrete, while the walls between offices are drywall.

The link-matrix of the Testbed looks like that (values in dBm):

```
Tx⟍Rx     1     2     3     4     5     6     7     8    10    11    12    13    14
     +-----------------------------------------------------------------------------
   1 |        -70   -84   -90
   2 |  -67         -77
   3 |  -81   -78         -70   -86
   4 |  -86         -69         -80
   5 |              -87   -81         -72
   6 |                          -72         -80                           -81
   7 |                                -83         -83                     -89
   8 |                                      -81               -86   -60   -80   -81
  10 |                                                              -81
  11 |                                            -85               -82
  12 |                                            -61   -86   -85
  13 |                                -83   -88   -81                           -63
  14 |                                            -79                     -61
```

:::{note}
Node 9 is permanently offline
:::

## Controlling the Testbed

Currently direct shell-access to the server is needed. From there [Shepherd-Herd](https://pypi.org/project/shepherd_herd) can be used to execute Tasks created by the [Core-Datalib](https://pypi.org/project/shepherd_core).

Top of the prio-list is to open an API-port to the internet. That would allow the testbed-client in the datalib to connect with the server remotely. In the near future each user-account can define experimental setups and the client transforms these to tasks, from patching the node-id into the firmware, over programming the targets, running the measurements and collecting the data for download.

Each Observer generates a hdf5-file. While we used shepherd in the past some postprocessing was generalized and bundled in the [main-datalib](https://pypi.org/project/shepherd_data). It is possible to extract logs, calculate metadata and generate plots.

### Example-workflow

First create an experiment and transform it to a task-set for the Testbed:

```Python
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models.content import EnergyEnvironment
from shepherd_core.data_models.content import Firmware
from shepherd_core.data_models.content import VirtualSourceConfig
from shepherd_core.data_models.experiment import Experiment
from shepherd_core.data_models.experiment import TargetConfig
from shepherd_core.data_models.task import TestbedTasks

xp1 = Experiment(
    name="rf_survey",
    comment="generate link-matrix",
    duration=4 * 60,
    target_configs=[
        TargetConfig(
            target_IDs=list(range(3000, 3010)),
            custom_IDs=list(range(0, 99)),  # note: longer list is OK
            energy_env=EnergyEnvironment(name="eenv_static_3300mV_50mA_3600s"),
            virtual_source=VirtualSourceConfig(name="direct"),
            firmware1=Firmware(name="nrf52_rf_survey"),
            firmware2=Firmware(name="msp430_deep_sleep"),
            power_tracing=None,
            gpio_tracing=GpioTracing(),
        )
    ],
)
TestbedTasks.from_xp(xp1).to_file("./tb_tasks_rf_survey.yaml")
```

Secondly transfer it to the testbed-server and run it:

```Shell
shepherd-herd run tb_tasks_rf_survey.yaml
```


## Related & Useful Links

- used [Hardware](../user/hardware) (Shepherd Cape, available Targets)
- available [firmwares for the targets](https://github.com/orgua/shepherd-targets)
    - adapted [Trafficbench](https://github.com/orgua/TrafficBench) for an [RF-survey](https://github.com/orgua/shepherd-targets/tree/main/nrf52_rf_survey)
- the [Trafficbench pythontool](https://pypi.org/project/trafficbench)
  - [Link-Matrix of the Testbed](https://github.com/orgua/shepherd-targets/issues/3#issuecomment-1816709179)

## Contributions

Feedback is more than welcome during that initial phase. Same for reusable & useful scripts or firmware you developed and want to donate.
