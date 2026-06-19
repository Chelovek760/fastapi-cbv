"""Class-based views for FastAPI routers.

Drop-in replacement for the unmaintained ``fastapi_utils.cbv``. The original
relied on ``APIRouter.include_router`` eagerly copying ``APIRoute`` objects into
``router.routes``; FastAPI 0.137 made ``include_router`` lazy (it appends an
internal ``_IncludedRouter`` placeholder), which broke ``fastapi_utils`` whenever
two ``@cbv`` decorators shared one router.

This implementation rebuilds each endpoint by re-adding it through the router's
public ``add_api_route`` / ``add_api_websocket_route`` API, which stays eager and
delegates all route-state computation back to FastAPI. Route configuration is
copied by introspecting ``add_api_route``'s own parameters, so the helper adapts
to upstream parameter changes instead of hard-coding a kwarg list.

Only the plain ``@cbv(router)`` form is supported (no ``*urls`` / ``set_responses``
helpers), which covers every call site in the codebase.
"""

import inspect
from collections.abc import Callable
from typing import Any, ClassVar, TypeVar, get_origin, get_type_hints

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute, APIWebSocketRoute

T = TypeVar("T")

CBV_CLASS_KEY = "__cbv_class__"


def cbv(router: APIRouter) -> Callable[[type[T]], type[T]]:
    """Convert the decorated class into a class-based view for ``router``.

    Methods of the class registered as endpoints on ``router`` become router
    endpoints whose first positional argument (``self``) is populated via
    FastAPI dependency injection of an instance of the class.

    Args:
        router: The router whose endpoints defined on the class should be bound.

    Returns:
        A class decorator.
    """

    def decorator(cls: type[T]) -> type[T]:
        _init_cbv(cls)
        _register_endpoints(router, cls)
        return cls

    return decorator


def _is_classvar(annotation: Any) -> bool:
    return annotation is ClassVar or get_origin(annotation) is ClassVar


def _init_cbv(cls: type[Any]) -> None:
    """Make class-annotated dependencies injectable.

    Rewrites ``__init__`` so that class-level annotated attributes are accepted as
    keyword-only dependencies and stored on the instance, and updates
    ``__signature__`` so FastAPI knows what to pass when resolving ``Depends(cls)``.
    """
    if getattr(cls, CBV_CLASS_KEY, False):
        return  # Already initialized
    old_init: Callable[..., Any] = cls.__init__
    old_signature = inspect.signature(old_init)
    old_parameters = list(old_signature.parameters.values())[1:]  # drop `self`
    new_parameters = [
        p for p in old_parameters if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]

    dependency_names: list[str] = []
    for name, hint in get_type_hints(cls).items():
        if _is_classvar(hint):
            continue
        dependency_names.append(name)
        new_parameters.append(
            inspect.Parameter(
                name=name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=hint,
                default=getattr(cls, name, inspect.Parameter.empty),
            )
        )
    new_signature = old_signature.replace(parameters=new_parameters)

    def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
        for dep_name in dependency_names:
            setattr(self, dep_name, kwargs.pop(dep_name))
        old_init(self, *args, **kwargs)

    cls.__signature__ = new_signature
    cls.__init__ = new_init
    cls.__cbv_class__ = True


def _register_endpoints(router: APIRouter, cls: type[Any]) -> None:
    functions = {func for _, func in inspect.getmembers(cls, inspect.isfunction)}
    cbv_routes = [
        route
        for route in list(router.routes)
        if isinstance(route, (APIRoute, APIWebSocketRoute)) and route.endpoint in functions
    ]
    prefix_length = len(router.prefix)
    for route in cbv_routes:
        _update_endpoint_signature(cls, route)
        router.routes.remove(route)
        path = route.path[prefix_length:]
        name = f"{cls.__name__}.{route.name}"
        if isinstance(route, APIWebSocketRoute):
            router.add_api_websocket_route(path, route.endpoint, name=name, dependencies=route.dependencies)
        else:
            router.add_api_route(path, route.endpoint, **_copy_route_kwargs(router, route, name))


def _copy_route_kwargs(router: APIRouter, route: APIRoute, name: str) -> dict[str, Any]:
    """Reconstruct ``add_api_route`` kwargs from an existing route.

    Pulls each parameter ``add_api_route`` accepts straight off the route object
    (attribute names match parameter names), so new/removed FastAPI parameters are
    handled automatically without editing this helper.
    """
    skip = {"self", "path", "endpoint", "name", "methods", "route_class_override"}
    sig = inspect.signature(router.add_api_route)
    kwargs: dict[str, Any] = {pname: getattr(route, pname) for pname in sig.parameters if pname not in skip}
    kwargs["name"] = name
    kwargs["methods"] = list(route.methods or [])
    if "route_class_override" in sig.parameters:
        kwargs["route_class_override"] = type(route)
    return kwargs


def _update_endpoint_signature(cls: type[Any], route: APIRoute | APIWebSocketRoute) -> None:
    """Inject ``Depends(cls)`` as the default for the endpoint's ``self`` parameter."""
    old_signature = inspect.signature(route.endpoint)
    old_parameters = list(old_signature.parameters.values())
    new_first = old_parameters[0].replace(default=Depends(cls))
    new_parameters = [new_first] + [p.replace(kind=inspect.Parameter.KEYWORD_ONLY) for p in old_parameters[1:]]
    route.endpoint.__signature__ = old_signature.replace(parameters=new_parameters)  # type: ignore[attr-defined]
