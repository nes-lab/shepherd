extracting Core-API with newer version (>=23.12.1) FAILs with

  File "/home/hans/.local/share/virtualenvs/shepherd-JJj2p24W/lib/python3.10/site-packages/shepherd_core/data_models/content/virtual_source.py", line 44, in Virtua
lSourceConfig
    harvester: VirtualHarvesterConfig = VirtualHarvesterConfig(name="mppt_opt")
  File "/home/hans/.local/share/virtualenvs/shepherd-JJj2p24W/lib/python3.10/site-packages/pydantic/main.py", line 171, in __init__
    self.__pydantic_validator__.validate_python(data, self_instance=self)
pydantic_core._pydantic_core.ValidationError: 1 validation error for Config for the Harvester
  Value error, Component 'virtualharvesterconfig' not found! [type=value_error, input_value={'name': 'mppt_opt'}, input_type=dict]

even when unittests of tools run through?!?

useful commands:

pip uninstall shepherd-core

git submodule update --recursive --remote
rm ~/.cache/shepherd/fixtures.pickle
pip install ../software/shepherd-tools/shepherd_core/
