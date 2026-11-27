"""Display transforms for exploratory inspection of image channels."""

import cv2
import numpy as np
from PIL import Image


def inspect_channel(image: Image.Image, space: str, channel: int) -> Image.Image:
    """Render one OpenCV component as an 8-bit grayscale image."""
    pixels = np.asarray(image)
    code = {"hsv": cv2.COLOR_RGB2HSV_FULL, "lab": cv2.COLOR_RGB2LAB}[space]
    converted = cv2.cvtColor(pixels, code)
    return Image.fromarray(converted[:, :, channel]).convert("RGB")


def local_equalization(image: Image.Image, clip_limit: float) -> Image.Image:
    """Equalize Lab luminance locally, retaining the two chromatic components."""
    lightness = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    lightness[:, :, 0] = clahe.apply(lightness[:, :, 0])
    return Image.fromarray(cv2.cvtColor(lightness, cv2.COLOR_LAB2RGB))


def component_view(image: Image.Image, component: int | None) -> Image.Image:
    """Render a PCA component or decorrelate and stretch the three RGB channels."""
    pixels = np.asarray(image).reshape(-1, 3)
    sample = pixels[:: max(1, len(pixels) // 100_000)].astype(np.float64)
    if len(sample) < 2:
        return image.copy()
    mean = sample.mean(axis=0)
    covariance = np.cov(sample, rowvar=False)
    _, vectors = np.linalg.eigh(covariance)
    vectors = vectors[:, ::-1]
    for axis in range(3):
        index = np.argmax(np.abs(vectors[:, axis]))
        if vectors[index, axis] < 0:
            vectors[:, axis] *= -1
    transformed = (sample - mean) @ vectors
    lower, upper = np.percentile(transformed, [2, 98], axis=0)
    out = np.empty((len(pixels), 3 if component is None else 1), dtype=np.uint8)
    gain = 255 / np.maximum(upper - lower, 1.0)
    for start in range(0, len(pixels), 400_000):
        sl = slice(start, start + 400_000)
        coordinates = (pixels[sl] - mean) @ vectors
        if component is None:
            stretched = (coordinates - (upper + lower) / 2) * gain
            values = stretched @ vectors.T + 127.5
        else:
            values = (coordinates[:, [component]] - lower[component]) * gain[component]
        out[sl] = np.clip(np.rint(values), 0, 255).astype(np.uint8)
    shape = (image.height, image.width) if component is not None else (image.height, image.width, 3)
    return Image.fromarray(out.reshape(shape)).convert("RGB")
