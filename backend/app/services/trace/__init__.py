"""Trace 服务：问答链路 Span 埋点 + 批量落库（Task 17）。"""
from app.services.trace.trace import SpanContext, Tracer

__all__ = ["Tracer", "SpanContext"]
