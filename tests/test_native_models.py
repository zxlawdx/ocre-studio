from pathlib import Path

import numpy as np
import pytest

from apps.model_library.native import NativeModelRegistry


def test_missing_native_model_has_actionable_error(tmp_path: Path) -> None:
    registry = NativeModelRegistry(tmp_path)
    assert not registry.available()
    with pytest.raises(ValueError, match="Recursos nativos"):
        registry.model("cpu")


def test_provisioned_weights_change_the_hybrid_output() -> None:
    registry = NativeModelRegistry()
    if not registry.available():
        pytest.skip("Native checkpoints have not been provisioned.")
    from apps.model_library.kokentau.kokentau_v8 import enhance

    pixels = np.random.default_rng(12).integers(35, 200, (92, 112, 3), dtype=np.uint8)
    roi = np.zeros(pixels.shape[:2], dtype=bool)
    roi[6:-6, 4:-4] = True
    model = registry.model("cpu")
    assert registry.model("cpu") is model
    native = model.process(pixels, roi, block=64)
    classical = enhance(pixels, roi, block=64)
    adaptive = model.adaptive(pixels, roi, block=64)
    assert native["combinado"].shape == pixels.shape == adaptive.shape
    assert np.array_equal(native["combinado"][~roi], pixels[~roi])
    assert np.array_equal(adaptive[~roi], pixels[~roi])
    assert not np.array_equal(native["combinado"][roi], classical["combinado"][roi])


def test_frozen_registry_prefers_bundle_and_honors_explicit_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    from apps.model_library.native import BUNDLED_MODELS

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Ocre-Studio.exe"))
    monkeypatch.delenv("OCRE_MODEL_DIR", raising=False)
    assert NativeModelRegistry().directory == tmp_path / BUNDLED_MODELS

    override = tmp_path / "diagnostics"
    monkeypatch.setenv("OCRE_MODEL_DIR", str(override))
    assert NativeModelRegistry().directory == override
