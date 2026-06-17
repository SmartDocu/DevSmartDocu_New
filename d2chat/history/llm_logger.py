# log_llm_call은 d2shared로 이동. 호환성을 위해 재노출.
from d2shared.llm_logger import log_llm_call  # noqa: F401

__all__ = ['log_llm_call']
