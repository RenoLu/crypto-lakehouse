"""Lazy, cached loader for the Kronos predictor.

All heavy imports (torch, the vendored model) happen inside get_predictor() so
that importing the API package never pulls in torch. The predictor is built once
and cached for the process lifetime.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import logger

if TYPE_CHECKING:
    from app.ml.kronos import KronosPredictor


@lru_cache(maxsize=1)
def get_predictor() -> "KronosPredictor":
    """Load the Kronos tokenizer + model and wrap them in a CPU predictor.

    Weights are fetched from the Hugging Face Hub on first call and cached in the
    local HF cache. Raises ImportError if the optional ``predict`` extra
    (torch, etc.) is not installed.
    """
    from app.ml.kronos import Kronos, KronosPredictor, KronosTokenizer

    logger.info(
        f"Loading Kronos predictor (tokenizer={settings.prediction_tokenizer}, "
        f"model={settings.prediction_model}, device=cpu)"
    )
    tokenizer = KronosTokenizer.from_pretrained(settings.prediction_tokenizer)
    model = Kronos.from_pretrained(settings.prediction_model)
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
    logger.info("Kronos predictor ready")
    return predictor
