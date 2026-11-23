"""The actuator that a scan moves to change a parameter of a waveform of the Waveform designer extension"""
from pymodaq_utils.utils import ThreadCommand

from pymodaq.control_modules.move_utility_classes import (
    DAQ_Move_base, DataActuator, DataActuatorType, comon_parameters_fun)


class DAQ_Move_WaveformParameter(DAQ_Move_base):
    """A virtual actuator, created by the Waveform designer extension (and closed with it)

    Its position is the value of one parameter of one waveform (the ``parameter`` setting, whose choices are set by the
    extension). Moving it asks the extension to compute the waveform with this value and to send it to the output
    actuator, and the move is done when the output actuator has loaded it.
    """
    _controller_units = ''
    is_multiaxes = False
    _epsilon = 1e-12
    data_actuator_type = DataActuatorType.DataActuator
    params = [{'title': 'Parameter:', 'name': 'parameter', 'type': 'list', 'limits': [],
               'tip': 'The parameter of a waveform that this actuator drives, listed by the extension'},
              ] + comon_parameters_fun(is_multiaxes, epsilon=_epsilon)

    def ini_attributes(self):
        self.controller = None
        self.value = DataActuator(data=0.)

    def ini_stage(self, controller=None):
        """The controller is the extension that created this actuator: nothing to initialize"""
        self.controller = controller
        return 'Waveform parameter of the Waveform designer', True

    def get_actuator_value(self) -> DataActuator:
        """The value of the chosen parameter, as it is in the settings of the extension"""
        self._take_value()
        return self.value

    def _take_value(self):
        """The value of the chosen parameter, read in the settings of the extension (the controller)"""
        value = self.controller.parameter_values().get(self.settings['parameter'])
        if value is not None:
            self.value = DataActuator(data=value)

    def close(self):
        pass

    def commit_settings(self, param):
        if param.name() == 'parameter':
            self.emit_value(self.get_actuator_value())

    def move_abs(self, position: DataActuator):
        """Ask the extension to build and send the waveform; ``waveform_loaded`` answers when it is done"""
        position = self.check_bound(position)
        self.target_value = position
        self.value = position
        self.emit_status(ThreadCommand('waveform_request', dict(parameter=self.settings['parameter'],
                                                                  position=position)))

    def waveform_loaded(self, ok: bool = True):
        """Command sent by the extension once the output actuator has loaded the waveform"""
        self.move_done()

    def move_rel(self, position: DataActuator):
        self.move_abs(self.value + position)

    def move_home(self):
        self.emit_status(ThreadCommand('Update_Status', ['A waveform parameter has no home position']))

    def stop_motion(self):
        self.move_done()
