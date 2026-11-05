import time

import numpy as np


class Cancelled(Exception):
    pass


class TimeLimitExceeded(Exception):
    pass


def solve_linear_system(matrix, vector, report, should_cancel, time_limit):
    a = np.array(matrix, dtype=float)
    b = np.array(vector, dtype=float)
    n = a.shape[0]
    started = time.monotonic()
    report(0, "Підготовка матриці")
    m = np.hstack([a, b.reshape(-1, 1)])
    for k in range(n):
        if should_cancel():
            raise Cancelled
        if time.monotonic() - started > time_limit:
            raise TimeLimitExceeded
        pivot = k + int(np.argmax(np.abs(m[k:, k])))
        if abs(m[pivot, k]) < 1e-12:
            raise ValueError("Matrix is singular")
        if pivot != k:
            m[[k, pivot]] = m[[pivot, k]]
        factors = m[k + 1 :, k] / m[k, k]
        m[k + 1 :, k:] -= np.outer(factors, m[k, k:])
        report(int((k + 1) * 90 / n), f"Виключення змінної {k + 1} з {n}")
    report(92, "Зворотна підстановка")
    x = np.zeros(n)
    for i in range(n - 1, -1, -1):
        x[i] = (m[i, -1] - m[i, i + 1 : n] @ x[i + 1 :]) / m[i, i]
    report(100, "Готово")
    return x.tolist()
