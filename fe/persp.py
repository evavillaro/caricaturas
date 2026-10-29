def persp_coeffs(pa, pb):
    """Coeficientes para Image.transform(PERSPECTIVE): pa = esquinas destino, pb = esquinas origen."""
    import numpy as np
    m = []
    for p1, p2 in zip(pa, pb):
        m.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        m.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    A = np.array(m, dtype=float); B = np.array([c for p in pb for c in p], dtype=float)
    return list(np.linalg.solve(A, B))
