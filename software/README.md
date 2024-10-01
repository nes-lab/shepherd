# Software for Shepherd-Testbed

A collection of components and subprojects needed for the testbed. Bold items are needed for a local shepherd instance.

- **`firmware`**: time-critical gpio-sampling and emulation of virtual power source in PRUs of BeagleBone
- `gps-overlay`: kernel-module to allow syncing time via GPS
- **`kernel-module`**: low level system interface in between sheep-software (python) and PRUs
- `openocd`: (semi-deprecated) configuration for programming targets via openOCD
- `pps-gmtimer`: kernel-module to sync to a pps-time-signal
- **`python-package`**: sheep-software running on the beaglebone
- `shepherd-calibration`: python-software to calibrate the cape using a Keithley Sourcemeter
- `shepherd-datalib`: sub-git for python user-module to handle measurements and access the data
- `shepherd-devicetest`: python-software to test & validate all parts of a cape
- **`shepherd-herd`**: python-software to control sheep / observers
- `shepherd-targets`: sub-git for target hardware and default firmwares
- `shepherd-webservice`: sub-git for the API and Website of the official testbed instance
- `debug_analyze_time_sync`: python-software for measuring sync between observers on gpio-level
