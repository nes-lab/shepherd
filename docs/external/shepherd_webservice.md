# Shepherd Webservice

**Source**: [https://github.com/orgua/shepherd_webservice](https://github.com/orgua/shepherd_webservice)

The Webservice links the user to the testbed. It's written in Python and uses FastAPI to expose an interface to the internet. You can write your own tools or just use the tb-client integrated in the [Core-Datalib](https://pypi.org/project/shepherd_core).

Internally the webservices utilizes the [herd-lib](https://pypi.org/project/shepherd_herd) to access the shepherd observers. Handling of data is done with Pydantic-Models that store the actual data a database.

----

**TODO**

- bring out of alpha-stage
- show structure, relations between sw-components
