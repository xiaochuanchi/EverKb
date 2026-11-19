"""API 统一信封。

EnvelopeRoute：response_model 校验后的 JSONResponse 二次包裹为
{"code": 0, "message": "ok", "data": ...}，status_code 原样保留；
非 JSONResponse（文件下载等）原样放行。业务 router 代码不感知信封。

异常映射：code = HTTP 状态码，HTTPException 的中文 detail 直接进 message。
必须在 HTTPException 与 StarletteHTTPException 两类上都注册——FastAPI
默认 handler 注册在精确类上，只注册父类会被 MRO 查找遮蔽回 {"detail": ...}。
"""
import json
import logging
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.datastructures import DefaultPlaceholder
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("everkb.api")


class EnvelopeRoute(APIRoute):
    """成功响应包信封；Response 子类（非 JSONResponse）原样放行。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # FastAPI 0.163.1：未显式指定 response_class（占位符或缺省）且有
        # response_model 时，handler 走 dump_json 快路径直接返回普通
        # Response（非 JSONResponse），信封包裹会被 isinstance 检查跳过。
        # 把占位符/缺省替换为具体 JSONResponse 以禁用快路径；显式传入的
        # response_class（如 PlainTextResponse）原样保留。
        response_class = kwargs.get("response_class")
        if response_class is None or isinstance(response_class, DefaultPlaceholder):
            kwargs["response_class"] = JSONResponse
        super().__init__(*args, **kwargs)

    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def envelope_handler(request: Request) -> Response:
            response = await original_handler(request)
            # 204/304 等 body-not-allowed 状态码会被 FastAPI 清空 body，
            # 无体可包，原样放行（json.loads(b"") 会炸成 500 信封）。
            # StreamingResponse/FileResponse/RedirectResponse 无 .body 属性，
            # 用 getattr 容忍，避免 AttributeError 同样被吃成 500 信封。
            if response.status_code in (204, 304) or not getattr(response, "body", None):
                return response
            if not isinstance(response, JSONResponse):
                return response
            return JSONResponse(
                status_code=response.status_code,
                content={"code": 0, "message": "ok", "data": json.loads(response.body)},
                # 透传端点设置的自定义 headers（Set-Cookie / Link 分页等）；
                # content-length 必剔（新 body 长度不同），content-type 由新
                # JSONResponse 重设为 application/json，保留旧值会冲突。
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in ("content-length", "content-type")
                },
                background=response.background,
            )

        return envelope_handler


def register_exception_handlers(app: FastAPI) -> None:
    """三类异常 → 信封；覆盖 FastAPI 默认 detail 格式（幂等）。"""

    async def http_to_envelope(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": exc.detail, "data": None},
            headers=exc.headers,
        )

    async def validation_to_envelope(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": 422, "message": "参数校验失败", "data": jsonable_encoder(exc.errors())},
        )

    async def unhandled_to_envelope(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("API 未处理异常")
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务器内部错误", "data": None},
        )

    app.add_exception_handler(HTTPException, http_to_envelope)
    app.add_exception_handler(StarletteHTTPException, http_to_envelope)
    app.add_exception_handler(RequestValidationError, validation_to_envelope)
    app.add_exception_handler(Exception, unhandled_to_envelope)
