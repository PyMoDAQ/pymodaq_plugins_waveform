"""A waveform output actuator without hardware, to test the applications of the contract"""
import time
import types

import numpy as np
from qtpy import QtWidgets

from pymodaq.control_modules import instruments
from pymodaq.control_modules.move_utility_classes import DAQ_Move_base, comon_parameters_fun, DataActuatorType
from pymodaq.utils.data import DataActuator
from pymodaq_plugins_utils.hardware.waveform_output import waveform_output_params, fill_waveform_output_settings, OutputMode


class DAQ_Move_FakeWaveformOutput(DAQ_Move_base):
    is_multiaxes = False
    _controller_units = 'V'
    _epsilon = 0.01
    data_actuator_type = DataActuatorType.DataActuator
    params = waveform_output_params() + comon_parameters_fun(is_multiaxes, epsilon=_epsilon)
    n_channels = 2

    def ini_attributes(self):
        self.controller = None
        self.loaded = None

    def ini_stage(self, controller=None):
        self.controller = object()
        self.loaded = DataActuator(data=[np.zeros(10)] * self.n_channels, units='V')
        fill_waveform_output_settings(self.settings, self.n_channels, 1., 1e5, 100000, -10., 10.,
                                      modes=(OutputMode.FINITE, OutputMode.REPEAT))
        return 'ok', True

    def get_actuator_value(self):
        return self.loaded

    def close(self):
        pass

    def commit_settings(self, param):
        pass

    def move_abs(self, position):
        self.target_value = position
        self.loaded = position
        self.move_done()

    def move_rel(self, position):
        pass

    def move_home(self):
        pass

    def stop_motion(self):
        pass


def register(name, plugin_class):
    if name not in instruments.ACTUATOR_NAMES:
        module = types.SimpleNamespace(**{f'daq_move_{name}': types.SimpleNamespace(**{f'DAQ_Move_{name}': plugin_class})})
        instruments.ACTUATOR_TYPES.append({'name': name, 'module': module, 'type': 'daq_move'})
        instruments.ACTUATOR_NAMES.append(name)


def make_module(name: str, title: str, timeout=10.):
    """An initialized DAQ_Move of a registered plugin"""
    import pymodaq.control_modules.daq_move as dm
    dm.find_actuator_class_from_name = instruments.find_actuator_class_from_name
    module = dm.DAQ_Move(None, title=title)  # no UI
    module.actuator = name
    inited = []
    module.init_signal.connect(inited.append)
    module.init_hardware(True)
    t0 = time.time()
    while not inited and time.time() - t0 < timeout:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert inited and inited[0], f'{name} did not initialize'
    return module
