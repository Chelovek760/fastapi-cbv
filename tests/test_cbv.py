import abc
from http import HTTPStatus
from typing import ClassVar

from fastapi import APIRouter, Depends, FastAPI, WebSocket
from fastapi.testclient import TestClient

from fastapi_cbv_router import CBV_CLASS_KEY, cbv


def _client(router: APIRouter) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _dependency() -> str:
    return "injected"


def test_dependency_injected_as_self_attribute() -> None:
    router = APIRouter()

    @cbv(router)
    class View:
        value: str = Depends(_dependency)

        @router.get("/value")
        def read(self) -> str:
            return self.value

    assert _client(router).get("/value").json() == "injected"


def test_classvar_is_not_injected() -> None:
    router = APIRouter()

    @cbv(router)
    class View:
        shared: ClassVar[str] = "constant"

        @router.get("/shared")
        def read(self) -> str:
            return self.shared

    response = _client(router).get("/shared")
    assert response.status_code == 200
    assert response.json() == "constant"


def test_class_attribute_default_becomes_optional_query_param() -> None:
    router = APIRouter()

    @cbv(router)
    class View:
        limit: int = 10

        @router.get("/items")
        def read(self) -> int:
            return self.limit

    client = _client(router)
    assert client.get("/items").json() == 10
    assert client.get("/items", params={"limit": 5}).json() == 5


def test_post_endpoint_and_router_prefix() -> None:
    router = APIRouter(prefix="/api")

    @cbv(router)
    class View:
        @router.post("/echo")
        def echo(self, payload: dict) -> dict:
            return payload

    response = _client(router).post("/api/echo", json={"a": 1})
    assert response.status_code == 200
    assert response.json() == {"a": 1}


def test_two_cbv_classes_share_one_router() -> None:
    # Regression: FastAPI 0.137 made include_router lazy, which broke
    # fastapi_utils whenever two @cbv decorators shared a single router.
    router = APIRouter()

    @cbv(router)
    class First:
        @router.get("/first")
        def read(self) -> str:
            return "first"

    @cbv(router)
    class Second:
        @router.get("/second")
        def read(self) -> str:
            return "second"

    client = _client(router)
    assert client.get("/first").json() == "first"
    assert client.get("/second").json() == "second"


def test_websocket_route() -> None:
    router = APIRouter()

    @cbv(router)
    class View:
        @router.websocket("/ws")
        async def socket(self, websocket: WebSocket) -> None:
            await websocket.accept()
            await websocket.send_text("hello")
            await websocket.close()

    with _client(router).websocket_connect("/ws") as ws:
        assert ws.receive_text() == "hello"


def test_custom_init_parameters_are_preserved() -> None:
    router = APIRouter()

    @cbv(router)
    class View:
        dep: str = Depends(_dependency)

        def __init__(self, multiplier: int = 2) -> None:
            self.multiplier = multiplier

        @router.get("/calc")
        def calc(self) -> str:
            return self.dep * self.multiplier

    assert _client(router).get("/calc").json() == "injectedinjected"


def test_hardcore_pattern_abc_base_with_injected_init() -> None:
    # Mirrors the real hardcore usage: the view inherits an abc.ABC port and
    # injects its dependencies through a custom __init__ with Depends-defaulted
    # parameters (no class-body dependencies), with status_code on the route.
    router = APIRouter(prefix="/p", tags=["p"])

    class Port(abc.ABC):
        @abc.abstractmethod
        async def read(self) -> str: ...

    @cbv(router)
    class Impl(Port):
        def __init__(self, service: str = Depends(_dependency)) -> None:
            self.service = service

        @router.get("/thing", status_code=HTTPStatus.OK)
        async def read(self) -> str:
            return self.service

    response = _client(router).get("/p/thing")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == "injected"


def test_decorated_class_is_marked() -> None:
    router = APIRouter()

    @cbv(router)
    class View:
        @router.get("/x")
        def read(self) -> str:
            return "x"

    assert getattr(View, CBV_CLASS_KEY) is True
