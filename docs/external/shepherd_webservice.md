# Webservice

[![QC-Tests](https://github.com/orgua/shepherd_webservice/actions/workflows/qc_tests.yml/badge.svg)](https://github.com/orgua/shepherd_webservice/actions/workflows/qc_tests.yml)

**Testbed-WebAPI**: <https://shepherd.cfaed.tu-dresden.de:8000>

**Documentation**: <https://orgua.github.io/shepherd/external/shepherd_webservice.html>

**Source Code**: <https://github.com/orgua/shepherd-webservice>

**Main Project**: <https://github.com/orgua/shepherd>

---

The Webservice links the user to the testbed. It's written in Python and uses FastAPI to expose an interface to the internet. You can write your own tools or just use the testbed-client integrated in the [Core-Datalib](https://pypi.org/project/shepherd_core).

Internally the webservices utilizes the [herd-lib](https://pypi.org/project/shepherd_herd) to access the shepherd observers. Handling of data is done with Pydantic-Models that store the actual data in a database.

## FastApi Webservice (current prototype)

- DNS approved for the server: shepherd.cfaed.tu-dresden.de
- Port 8000 requested for firewall passing
  - SSL-Certificate per LetsEncrypt -> alternative is <www.sectigo.com>
  - bring demo-application online
  - add [https to FastAPI](https://fastapi.tiangolo.com/deployment/https/)
- TODO: allow service to start with reduced rights -> get nfs in order (access needs elevation)

[API-Website](http://127.0.0.1:8000/)
[ReDoc](http://127.0.0.1:8000/doc)
[OpenApiDoc](http://127.0.0.1:8000/doc0)


----

## Cornerstones

### Data-Containers

[Pydantic](https://github.com/pydantic/pydantic)

- data validation for python dataclasses, its fast, elegantly designed and comes with batteries included
- already trusted base for [shepherd-datalib](https://github.com/orgua/shepherd-datalib)

### WebFrontend

[FastUI](https://github.com/pydantic/FastUI)

- restful web-framework based on pydantic2 & fastapi
- still alpha, but usable, rapid updates
- plan B: tbd

[Streamlit](https://streamlit.io)
- stable and lots to offer, but maybe limited for more
- and there is a freemium service

### WebApi

[FastApi](https://fastapi.tiangolo.com/)
- high performance web framework for APIs based on pydantic
- offers features like OAuth, SSL-Encryption (by uvicorn), user-sessions
- **choice for now**

[Flask](https://flask.palletsprojects.com/en/3.0.x/)
- low level but stable framework

### Database

[Beanie](https://github.com/roman-right/beanie)
- async & pydantic-based ODM or MongoDB
- stable, but also actively developed
- **choice for now**

[SQLModel](https://github.com/tiangolo/sqlmodel)
- async & pydantic-based ODM for SQLAlchemy
- still alpha, very slow in development
- has trouble with complex pydantic-models

[ORMDantic](https://github.com/yezz123/ormdantic)
- async & pydantic-based ODM for SQLAlchemy
- currently limited to pydantic <v2 -> dealbreaker

### Misc

- Secrets-Management
  - https://pypi.org/project/python-secrets/
- Server-Monitoring, remote alerting
  - sentry-sdk,


## install

- set up a local MongoDB instance
- install package
- config .env, by either bringing in a backup or starting fresh
  - backup: repopulate database by using ´shepherd_wsrv init file´
  - fresh start: generate [fresh salt](https://github.com/orgua/shepherd_webservice/blob/main/scripts/salt_generator.py) and initialize database with `shepherd_wsrv init`

## run server

```Shell
shepherd_wsrv run
```

or to switch to the offline-mode activate the redirect to the docs

```Shell
shepherd_wsrv redirect
```

## save state

```Shell
shepherd_wsrv backup file_name
```
