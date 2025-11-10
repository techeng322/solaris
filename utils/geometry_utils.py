"""
Geometry utility functions for 3D calculations.
"""

import math
from typing import Tuple


def calculate_distance(point1: Tuple[float, float, float], point2: Tuple[float, float, float]) -> float:
    """
    Calculate Euclidean distance between two 3D points.
    
    Args:
        point1: First point (x, y, z)
        point2: Second point (x, y, z)
    
    Returns:
        Distance in meters
    """
    dx = point2[0] - point1[0]
    dy = point2[1] - point1[1]
    dz = point2[2] - point1[2]
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def calculate_angle(vector1: Tuple[float, float, float], vector2: Tuple[float, float, float]) -> float:
    """
    Calculate angle between two 3D vectors in degrees.
    
    Args:
        vector1: First vector
        vector2: Second vector
    
    Returns:
        Angle in degrees
    """
    dot_product = sum(v1 * v2 for v1, v2 in zip(vector1, vector2))
    mag1 = math.sqrt(sum(v * v for v in vector1))
    mag2 = math.sqrt(sum(v * v for v in vector2))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    cos_angle = dot_product / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    angle_rad = math.acos(cos_angle)
    return math.degrees(angle_rad)


def normalize_vector(vector: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    Normalize a 3D vector to unit length.
    
    Args:
        vector: Input vector
    
    Returns:
        Normalized vector
    """
    magnitude = math.sqrt(sum(v * v for v in vector))
    if magnitude == 0:
        return (0.0, 0.0, 0.0)
    return tuple(v / magnitude for v in vector)

