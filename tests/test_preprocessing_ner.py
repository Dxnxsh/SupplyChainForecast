"""Tests for GLiNER2-based NER location extraction in preprocessing.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_extract_locations_batch_empty_input():
    """Empty input returns empty list without loading model."""
    from src.preprocessing import extract_locations_batch

    result = extract_locations_batch([])
    assert result == []


def test_extract_locations_batch_returns_correct_shape():
    """Output is List[List[str]] with one entry per input text."""
    from src.preprocessing import extract_locations_batch

    mock_model = MagicMock()
    mock_model.batch_extract_entities.return_value = [
        {"entities": {"location": ["Taiwan"]}},
        {"entities": {"location": ["Shanghai", "Beijing"]}},
        {"entities": {"location": []}},
    ]

    with patch("src.preprocessing.get_ner_pipeline", return_value=mock_model):
        result = extract_locations_batch(["text about Taiwan", "Shanghai and Beijing news", "no locations here"])

    assert len(result) == 3
    assert "Taiwan" in result[0]
    assert set(result[1]) == {"Shanghai", "Beijing"}
    assert result[2] == []


def test_extract_locations_batch_handles_none_texts():
    """None values in input are coerced to empty strings."""
    from src.preprocessing import extract_locations_batch

    mock_model = MagicMock()
    mock_model.batch_extract_entities.return_value = [
        {"entities": {"location": []}},
        {"entities": {"location": []}},
    ]

    with patch("src.preprocessing.get_ner_pipeline", return_value=mock_model):
        result = extract_locations_batch([None, ""])

    assert len(result) == 2
    call_args = mock_model.batch_extract_entities.call_args[0]
    assert all(isinstance(t, str) for t in call_args[0])


def test_extract_locations_batch_error_returns_empty_lists():
    """On exception, returns empty lists and warns once."""
    import warnings
    from src.preprocessing import extract_locations_batch

    mock_model = MagicMock()
    mock_model.batch_extract_entities.side_effect = RuntimeError("GPU exploded")

    extract_locations_batch._warned = False

    with patch("src.preprocessing.get_ner_pipeline", return_value=mock_model):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = extract_locations_batch(["some text", "other text"])

    assert result == [[], []]
    assert len(w) == 1
    assert "GLiNER2" in str(w[0].message)


def test_get_ner_pipeline_loads_gliner2():
    """get_ner_pipeline loads GLiNER2 model with correct model ID and device."""
    import src.preprocessing as prep

    mock_gliner_cls = MagicMock()
    mock_model_instance = MagicMock()
    mock_gliner_cls.from_pretrained.return_value = mock_model_instance
    mock_model_instance.to.return_value = mock_model_instance

    prep._gliner_model = None

    with patch("src.preprocessing.GLiNER2", mock_gliner_cls):
        with patch("src.preprocessing._select_torch_device", return_value=(-1, "cpu")):
            with patch.dict("os.environ", {"GLINER_MODEL": "fastino/gliner2-large-v1"}):
                model = prep.get_ner_pipeline()

    mock_gliner_cls.from_pretrained.assert_called_once_with("fastino/gliner2-large-v1")
    mock_model_instance.to.assert_called_once_with(-1)
    assert model is mock_model_instance

    prep._gliner_model = None


def test_unload_ner_clears_singleton():
    """unload_ner sets the global to None and calls GC."""
    import src.preprocessing as prep

    prep._gliner_model = MagicMock()

    with patch("gc.collect") as mock_gc:
        prep.unload_ner()

    assert prep._gliner_model is None
    assert mock_gc.called
