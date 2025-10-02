"""
Langfuse tracing integration for LangGraph monitoring and cost tracking.
"""
import os
import logging
from typing import Optional, Dict, Any
from langfuse import Langfuse
try:
    from langfuse.decorators import observe, langfuse_context
    _has_decorators = True
except ImportError:
    _has_decorators = False

logger = logging.getLogger(__name__)

# Initialize Langfuse client
_langfuse_client: Optional[Langfuse] = None
_langfuse_enabled = False

try:
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
        _langfuse_client = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST
        )
        _langfuse_enabled = True
        logger.info("Langfuse tracing enabled: host=%s", LANGFUSE_HOST)
    else:
        logger.info("Langfuse tracing disabled: missing API keys")
except Exception as e:
    logger.exception("Failed to initialize Langfuse: %s", e)
    _langfuse_enabled = False


def is_enabled() -> bool:
    """Check if Langfuse is enabled."""
    return _langfuse_enabled


def get_langfuse_handler():
    """Get Langfuse callback handler for LangChain/LangGraph."""
    if not _langfuse_enabled or not _langfuse_client:
        return None
    try:
        # Try newer API first (langfuse >= 2.0)
        try:
            from langfuse.callback import CallbackHandler
            return CallbackHandler(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
            )
        except ImportError:
            # Fallback for older versions
            logger.warning("CallbackHandler not available in this Langfuse version")
            return None
    except Exception as e:
        logger.exception("Failed to create Langfuse handler: %s", e)
        return None


def trace_gemini_call(prompt: str, response: str, model: str, metadata: Optional[Dict[str, Any]] = None):
    """Manually trace a Gemini API call."""
    if not _langfuse_enabled or not _langfuse_client:
        return
    try:
        # Estimate tokens (rough: 4 chars ≈ 1 token)
        prompt_tokens = len(prompt) // 4
        completion_tokens = len(response) // 4
        
        # Langfuse 2.x API - use generation
        _langfuse_client.generation(
            name="gemini_generate",
            model=model,
            input=prompt[:1000],
            output=response[:1000],
            usage={
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": prompt_tokens + completion_tokens
            },
            metadata=metadata or {}
        )
    except Exception as e:
        logger.debug("Failed to trace Gemini call: %s", e)


def trace_exa_search(query: str, results: list, metadata: Optional[Dict[str, Any]] = None):
    """Manually trace an Exa search."""
    if not _langfuse_enabled or not _langfuse_client:
        return
    try:
        _langfuse_client.span(
            name="exa_search",
            input={"query": query},
            output={"count": len(results), "results": results[:3]},
            metadata=metadata or {}
        )
    except Exception as e:
        logger.debug("Failed to trace Exa search: %s", e)


def trace_rag_operation(operation: str, input_data: Dict[str, Any], output_data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
    """Trace RAG operations (upsert, retrieve)."""
    if not _langfuse_enabled or not _langfuse_client:
        return
    try:
        _langfuse_client.span(
            name=f"rag_{operation}",
            input=input_data,
            output=output_data,
            metadata=metadata or {}
        )
    except Exception as e:
        logger.debug("Failed to trace RAG operation: %s", e)


def flush():
    """Flush pending traces to Langfuse."""
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception as e:
            logger.debug("Failed to flush Langfuse: %s", e)

