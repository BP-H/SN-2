from typing import Callable

from fastapi import APIRouter


def create_system_votes_router(
    *,
    get_system_vote_endpoint: Callable,
    get_system_vote_config_endpoint: Callable,
    cast_system_vote_endpoint: Callable,
    remove_system_vote_endpoint: Callable,
) -> APIRouter:
    router = APIRouter()

    router.add_api_route(
        "/system-vote",
        get_system_vote_endpoint,
        methods=["GET"],
    )
    router.add_api_route(
        "/system-vote/config",
        get_system_vote_config_endpoint,
        methods=["GET"],
    )
    router.add_api_route(
        "/system-vote",
        cast_system_vote_endpoint,
        methods=["POST"],
    )
    router.add_api_route(
        "/system-vote",
        remove_system_vote_endpoint,
        methods=["DELETE"],
    )

    return router
