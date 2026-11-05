"""errors.py — 统一错误码与领域异常层级。

对外错误只含可处理信息；内部栈信息不进响应、不进模型上下文（方案 §13.4）。
"""
from __future__ import annotations


class LedgerError(Exception):
    code = "INTERNAL"
    http_status = 500
    retryable = False
    default_message = "服务内部错误"

    def __init__(self, message="", *, field_errors=None, retryable=None):
        super().__init__(message)
        self.message = message or self.default_message
        self.field_errors = field_errors or []
        if retryable is not None:
            self.retryable = retryable

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "field_errors": self.field_errors,
            "retryable": self.retryable,
        }


class InvalidArgument(LedgerError):
    code = "INVALID_ARGUMENT"
    http_status = 422
    default_message = "参数不合法"


class NotFound(LedgerError):
    code = "NOT_FOUND"
    http_status = 404
    default_message = "资源不存在"


class VersionConflict(LedgerError):
    code = "VERSION_CONFLICT"
    http_status = 409
    default_message = "数据已被修改，请刷新后重试"


class IdempotencyConflict(LedgerError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409
    default_message = "相同幂等键的参数不一致"


class ConfirmationRequired(LedgerError):
    code = "CONFIRMATION_REQUIRED"
    http_status = 409
    default_message = "该操作需要确认"


class RateLimited(LedgerError):
    code = "RATE_LIMITED"
    http_status = 429
    retryable = True
    default_message = "请求过于频繁"


class ProviderUnavailable(LedgerError):
    code = "PROVIDER_UNAVAILABLE"
    http_status = 503
    retryable = True
    default_message = "外部服务不可用"


class PayloadTooLarge(LedgerError):
    code = "PAYLOAD_TOO_LARGE"
    http_status = 413
    default_message = "上传内容超限"
