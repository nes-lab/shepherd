# Webservice

[![Repo-Tests](https://github.com/orgua/shepherd_webservice/actions/workflows/repo-tests.yml/badge.svg)](https://github.com/orgua/shepherd_webservice/actions/workflows/repo-tests.yml)

**Documentation**: <https://orgua.github.io/shepherd/external/shepherd_webservice.html>

**Source Code**: <https://github.com/orgua/shepherd-webservice>

**Main Project**: <https://github.com/orgua/shepherd>

---

The Webservice links the user to the testbed. It's written in Python and uses FastAPI to expose an interface to the internet. You can write your own tools or just use the tb-client integrated in the [Core-Datalib](https://pypi.org/project/shepherd_core).

Internally the webservices utilizes the [herd-lib](https://pypi.org/project/shepherd_herd) to access the shepherd observers. Handling of data is done with Pydantic-Models that store the actual data a database.

## FastApi Webservice

- DNS approved for the server: shepherd.cfaed.tu-dresden.de
- Port 8000 requested for firewall passing
  - SSL-Certificate per LetsEncrypt -> alternative is <www.sectigo.com>
  - bring demo-application online
  - add [https to FastAPI](https://fastapi.tiangolo.com/deployment/https/)
- TODO: allow service to start with reduced rights -> get nfs in order (access needs elevation)

----

**TODO**

- bring out of alpha-stage
- show structure, relations between sw-components
