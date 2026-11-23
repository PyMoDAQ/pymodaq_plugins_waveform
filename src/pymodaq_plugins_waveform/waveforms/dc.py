"""Constant level"""
import dataclasses
from typing import ClassVar

import numpy as np

from pymodaq_plugins_waveform.waveform_factory import (Waveform, WaveformFactory, waveform_field)


@WaveformFactory.register()
@dataclasses.dataclass
class DC(Waveform):
    name: ClassVar[str] = 'dc'
    level: float = waveform_field(0., 'V', 'Level')
    duration: float = waveform_field(1e-3, 's', 'Duration', min=0.)

    def _to_samples(self, sample_rate):
        return np.full(self.n_samples(sample_rate), self.level), None
