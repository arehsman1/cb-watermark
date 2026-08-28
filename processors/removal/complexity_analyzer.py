import numpy as np
from config import EDGE_DENSITY_THRESHOLD, LAPLACIAN_VARIANCE_THRESHOLD

def analyze_complexity(gray_region):
    import cv2
    if gray_region.size == 0:
        return {"edge_density": 0.0, "laplacian_variance": 0.0, "is_complex": False}
    edges = cv2.Canny(gray_region, 50, 150)
    edge_density = float(np.count_nonzero(edges)) / edges.size
    laplacian_variance = float(cv2.Laplacian(gray_region, cv2.CV_64F).var())
    return {
        "edge_density": edge_density,
        "laplacian_variance": laplacian_variance,
        "is_complex": (
            edge_density > EDGE_DENSITY_THRESHOLD
            or laplacian_variance > LAPLACIAN_VARIANCE_THRESHOLD
        ),
    }
