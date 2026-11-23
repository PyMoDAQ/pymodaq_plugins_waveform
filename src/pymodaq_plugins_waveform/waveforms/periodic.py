"""Helpers of the periodic waveforms"""
import numpy as np


def period(frequency: float, sample_rate: float) -> tuple[int, float]:
    """Number of samples of a period and the frequency that is really generated with it

    A looped buffer holds a whole number of periods, so the frequency is the one of the closest whole number of
    samples per period.
    """
    if frequency <= 0:
        raise ValueError('The frequency should be positive')
    if frequency > sample_rate / 2:
        raise ValueError(f'The frequency {frequency} Hz is above half the sample rate {sample_rate} Hz')
    n = int(round(sample_rate / frequency))
    return n, sample_rate / n


def phase(n: int, phase_deg: float) -> np.ndarray:
    """The position in the period (0 to 1, going around) of each of the n samples"""
    return (np.arange(n) / n + phase_deg / 360.) % 1.
