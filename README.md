# fastapi-cbv-router

[![CI](https://github.com/Chelovek760/fastapi-cbv/actions/workflows/ci.yml/badge.svg)](https://github.com/Chelovek760/fastapi-cbv/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/fastapi-cbv-router)](https://pypi.org/project/fastapi-cbv-router/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastapi-cbv-router)](https://pypi.org/project/fastapi-cbv-router/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Class-based views (CBV) for FastAPI routers — a small, maintained drop-in
replacement for the unmaintained `fastapi_utils.cbv`. Works on modern FastAPI
(tested from 0.115), and in particular survives FastAPI 0.137+, where
`fastapi_utils.cbv` breaks.

## Why

`fastapi_utils.cbv` relied on `APIRouter.include_router` eagerly copying
`APIRoute` objects into `router.routes`. FastAPI 0.137 made `include_router`
lazy, which broke `fastapi_utils` whenever two `@cbv` decorators shared one
router.

`fastapi-cbv-router` rebuilds each endpoint through the router's public
`add_api_route` / `add_api_websocket_route` API, which stays eager and
delegates all route-state computation back to FastAPI. Route configuration is
copied by introspecting `add_api_route`'s own parameters, so the package adapts
to upstream FastAPI changes instead of hard-coding a kwarg list.

## Features

- One small decorator, `@cbv(router)` — no base classes or metaclasses required.
- Share a single dependency instance (`self`) across every endpoint on a class.
- Inject dependencies either as **class-level annotated attributes** or through a
  **custom `__init__`** — use whichever fits your style.
- Works with regular HTTP routes **and** WebSocket routes.
- Preserves all route configuration (`status_code`, `response_model`,
  `dependencies`, tags, …) and the router `prefix`.
- Fully typed (`py.typed`), zero dependencies beyond FastAPI.

## Requirements

- **Python:** 3.13+
- **FastAPI:** 0.115+ — continuously tested against the latest release, currently
  **0.137.2**. The test suite specifically covers FastAPI 0.137+, where
  `include_router` became lazy and broke `fastapi_utils.cbv`.

## Install

```bash
pip install fastapi-cbv-router
# or
uv add fastapi-cbv-router
```

## Quickstart

```python
from fastapi import APIRouter, Depends, FastAPI
from fastapi_cbv_router import cbv

router = APIRouter(prefix="/items")


def get_db() -> str:
    return "db-connection"


@cbv(router)
class ItemsView:
    db: str = Depends(get_db)

    @router.get("/")
    def list_items(self) -> dict:
        return {"db": self.db, "items": []}

    @router.post("/")
    def create_item(self, name: str) -> dict:
        return {"db": self.db, "created": name}


app = FastAPI()
app.include_router(router)
```

Class-level annotated attributes become keyword-only dependencies injected via
`Depends(ItemsView)` and are available as `self.<attr>` in every endpoint.
`ClassVar`-annotated attributes are treated as plain class constants and are not
injected.

## Dependency injection via `__init__`

If you prefer constructor injection — for example to keep a clean abstract base
and wire dependencies explicitly — define a custom `__init__`. Its parameters
are resolved by FastAPI when the view is constructed, exactly like an endpoint's
parameters:

```python
import abc
from http import HTTPStatus

from fastapi import APIRouter, Depends
from fastapi_cbv_router import cbv

router = APIRouter(prefix="/items", tags=["items"])


def get_service() -> "ItemService":
    ...


class ItemApi(abc.ABC):
    @abc.abstractmethod
    async def get_item(self, item_id: int) -> dict: ...


@cbv(router)
class HttpItemApi(ItemApi):
    def __init__(self, service: "ItemService" = Depends(get_service)) -> None:
        self.service = service

    @router.get("/{item_id}", status_code=HTTPStatus.OK)
    async def get_item(self, item_id: int) -> dict:
        return await self.service.fetch(item_id)
```

This pairs cleanly with DI containers such as
[`dependency-injector`](https://python-dependency-injector.ets-labs.org/): use
`Depends(Provide[...])` defaults on the `@inject`-decorated `__init__`.

## WebSocket routes

WebSocket endpoints are supported the same way as HTTP routes:

```python
from fastapi import APIRouter, WebSocket
from fastapi_cbv_router import cbv

router = APIRouter()


@cbv(router)
class ChatView:
    @router.websocket("/ws")
    async def chat(self, websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("hello")
        await websocket.close()
```

## Scope

Only the plain `@cbv(router)` form is supported (no `*urls` / `set_responses`
helpers). This is intentional — it covers the common case with the smallest,
most maintainable surface.

## License

MIT
