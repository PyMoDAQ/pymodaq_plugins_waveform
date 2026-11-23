"""Dashboard extension to design waveforms and send them to a waveform output actuator

The waveforms are the ones of the :class:`~pymodaq_plugins_waveform.waveform_factory.WaveformFactory`. The target is one
of the actuators of the Dashboard that follow the contract of
:mod:`pymodaq_plugins_utils.hardware.waveform_output`. The extension can also create virtual actuators
(``Waveform parameter``) that a scan moves to change one parameter of a waveform: they ask the extension to compute and
send the waveform, and they are closed with it.
"""
from typing import Optional, TYPE_CHECKING

import numpy as np
from qtpy import QtCore, QtWidgets

from pymodaq.control_modules.enums import DAQTypesEnum  # noqa: F401  (kept for the ones that subclass)
from pymodaq.control_modules.utils import ControllerAndThread, QThreadProxy
from pymodaq.utils.custom_ext import CustomExt
from pymodaq.utils.managers.modules import ModuleType
from pymodaq.utils.managers.modules.loader import PluginInfo
from pymodaq.utils.data import Axis, DataRaw, DataToExport, DataActuator
from pymodaq_gui import utils as gutils
from pymodaq_gui.plotting.data_viewers.viewer import ViewerDispatcher
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.utils import ThreadCommand
from pymodaq_plugins_utils.hardware.waveform_output import (
    WaveformOutput, OutputMode, OUTPUT_NAME, waveform_output_settings_params)

from pymodaq_plugins_waveform import waveforms  # noqa: F401  (registers the waveforms)
from pymodaq_plugins_waveform.waveform_factory import Waveform, WaveformFactory
from pymodaq_plugins_waveform.waveform_manager import WaveformManager

if TYPE_CHECKING:
    from pymodaq.control_modules.daq_move import DAQ_Move

logger = set_logger(get_module_name(__file__))

EXTENSION_NAME = 'Waveform designer'  # the name displayed in the extension list of the dashboard
CLASS_NAME = 'WaveformDesigner'
PARAMETER_ACTUATOR = 'Waveform parameter'  # name of the virtual actuators
PARAMETER_PLUGIN = 'WaveformParameter'  # the instrument plugin of these actuators
DEFAULT_WAVEFORM = 'sine'


def channel_group(index: int, waveform: str = DEFAULT_WAVEFORM) -> dict:
    """Settings of one channel: the choice of the waveform and its parameters, from the factory"""
    return {'title': f'Channel {index + 1}', 'name': f'ch{index}', 'type': 'group', 'children': [
        {'title': 'Waveform:', 'name': 'waveform', 'type': 'list', 'limits': WaveformFactory.names(),
         'value': waveform},
        {'title': 'Parameters:', 'name': 'parameters', 'type': 'group',
         'children': WaveformFactory.get_class(waveform).params()}]}


def parameter_key(channel: int, name: str) -> str:
    """What the ``parameter`` setting of a virtual actuator holds"""
    return f'Channel {channel + 1}: {name}'


class WaveformDesigner(CustomExt):
    # emitted by the virtual actuators (they run in their own thread, the settings and the send are of the GUI thread:
    # the connection is queued): the text of their ``parameter`` setting and the position asked
    parameter_requested = QtCore.Signal(str, float)
    settings_name = 'WaveformDesignerSettings'
    h5_base_group_name = 'WaveformDesigner'
    params = [
        {'title': 'Target:', 'name': 'target', 'type': 'list', 'limits': [],
         'tip': 'Actuators of the Dashboard that are waveform outputs'},
        waveform_output_settings_params(),
        {'title': 'Channels:', 'name': 'channels', 'type': 'group', 'children': []},
    ]

    def __init__(self, parent: gutils.DockArea, dashboard):
        super().__init__(parent, dashboard, add_toolbar_break=False)
        self._parameter_actuators: list[str] = []
        self._connected_targets: set[str] = set()
        self._waiting_for_target = False
        self._silent = False  # True while the settings are changed by the extension: no preview for each change
        self.setup_ui()
        self.show_repetitions()
        self.dashboard.modules_manager.modules_added_signal.connect(self.on_modules_added)
        self.parameter_requested.connect(self.on_parameter_request)
        self.refresh_targets()
        self.setup_waveform_manager()

    def setup_waveform_manager(self):
        """The manager of the saved waveforms: its actions are in a toolbar of the extension, its window is not shown.
        It is made once the channels exist, as it saves them in its default entry."""
        self.waveform_manager = WaveformManager(designer=self)
        self.waveform_manager.add_to_toolbar(self.add_toolbar('waveform_manager', 'Waveforms', parent=self.mainwindow, add_break=False))

    # ---- the interface
    def setup_docks_and_widgets(self):
        self.docks['settings'] = gutils.Dock('Settings')
        self.dockarea.addDock(self.docks['settings'])
        self.docks['settings'].addWidget(self.settings_tree)

        self.docks['preview'] = gutils.Dock('Preview')
        self.dockarea.addDock(self.docks['preview'], 'right')
        area_preview = gutils.DockArea()
        self.docks['preview'].addWidget(area_preview)
        self.preview = ViewerDispatcher(area_preview, direction='bottom')

    def setup_actions(self):
        self.add_action('refresh', 'Refresh targets', 'refresh', 'Look again for the waveform output actuators')
        self.add_action('preview', 'Preview', 'visibility', 'Compute the waveforms and show them')
        self.add_action('send', 'Send', 'start', 'Send the waveforms to the target actuator')
        self.add_action('stop', 'Stop', 'stop', 'Stop the output of the target actuator')
        self.add_action('create_parameter_actuator', 'Create a parameter actuator', 'add_circle',
                        tip=f'Create a "{PARAMETER_ACTUATOR}" actuator that a scan can move to change a parameter')

    def connect_things(self):
        self.connect_action('refresh', self.refresh_targets)
        self.connect_action('preview', self.show_preview)
        self.connect_action('send', self.send)
        self.connect_action('stop', self.stop)
        self.connect_action('create_parameter_actuator', self.create_parameter_actuator)

    def setup_menus_and_toolbars(self, menubar: QtWidgets.QMenuBar = None):
        self.create_dashboard_toolbar(add_break=False)
    def get_app_toolbars(self) -> list[QtWidgets.QToolBar]:
        """The toolbars shown in the window of the extension: also the one of the manager"""
        return [self.toolbar, self.get_toolbar('waveform_manager')]

    def validate_config(self) -> bool:
        return True

    @property
    def config_path(self):
        return None

    # ---- the target
    def target_modules(self) -> dict[str, 'DAQ_Move']:
        """The actuators of the Dashboard that follow the contract of the waveform outputs"""
        return {module.title: module for module in self.modules_manager.actuators_all
                if WaveformOutput.from_module(module) is not None}

    def refresh_targets(self):
        """Update the list of targets, and the channels if the target changed"""
        modules = self.target_modules()
        for title, module in modules.items():
            if title not in self._connected_targets:
                self._connected_targets.add(title)
                module.move_done_signal.connect(self._on_target_done)
        targets = list(modules)
        target = self.settings.child('target')
        current = target.value()
        target.setLimits(targets)
        if current in targets:
            target.setValue(current)
        elif targets:
            target.setValue(targets[0])
            self.target_changed()
        else:
            self.target_changed()

    def on_modules_added(self):
        """Instruments were added to the Dashboard after the experiment was set: the manager of the extension does not
        see them (it takes the list of the Dashboard when an experiment is set, and a new list is made when modules are
        added), so take it again. A removal changes the list that both share."""
        self.modules_manager.actuators_all = self.dashboard.modules_manager.actuators_all
        self.refresh_targets()

    def do_things_after_experiment_set(self, experiment_name: str, show_dashboard: bool = None):
        """The instruments changed: look again for the targets"""
        super().do_things_after_experiment_set(experiment_name, show_dashboard)
        self.refresh_targets()

    @property
    def target(self) -> Optional['DAQ_Move']:
        return self.target_modules().get(self.settings['target'])

    def target_changed(self):
        """One group of settings per channel of the target (one without target), and the output choices of the target"""
        module = self.target
        output = WaveformOutput.from_module(module) if module is not None else None
        self._silent = True
        try:
            self._build_channels(output)
        finally:
            self._silent = False
        self.show_preview()

    def _build_channels(self, output: Optional[WaveformOutput]):
        """Create the settings of the channels (and take the output choices) for the capabilities of the target"""
        channels = self.settings.child('channels')
        if output is None:  # no target: one channel to design and preview waveforms, kept if there already are some
            if not channels.children():
                channels.addChild(channel_group(0))
                self.update_parameter_choices()
            return
        channels.clearChildren()
        for index in range(output.n_channels):
            channels.addChild(channel_group(index))
        for name, value in (('sample_rate', output.sample_rate), ('mode', output.mode.value),
                            ('repetitions', output.repetitions)):
            self.settings.child(OUTPUT_NAME, name).setValue(value)
        self.settings.child(OUTPUT_NAME, 'mode').setLimits([mode.value for mode in output.modes])
        self.show_repetitions()
        self.update_parameter_choices()

    def show_repetitions(self):
        """The repetitions are only used by the ``repeat`` mode"""
        self.settings.child(OUTPUT_NAME, 'repetitions').setOpts(
            visible=self.settings[OUTPUT_NAME, 'mode'] == OutputMode.REPEAT.value)

    def value_changed(self, param):
        """The preview follows every change of a waveform or of the sample rate"""
        if self._silent:
            return
        if param.name() == 'target':
            self.target_changed()
        elif param.name() == 'waveform' and param.parent().name().startswith('ch'):
            self._silent = True
            try:
                parameters = param.parent().child('parameters')
                parameters.clearChildren()
                parameters.addChildren(WaveformFactory.get_class(param.value()).params())
                self.update_parameter_choices()
            finally:
                self._silent = False
        path = self.settings.childPath(param) or []
        if path == [OUTPUT_NAME, 'mode']:
            self.show_repetitions()
        if len(path) == 4 and path[0] == 'channels' and path[2] == 'parameters':
            self.update_parameter_actuators(parameter_key(int(path[1][2:]), path[3]))
        if path and (path[0] == 'channels' or path[:2] == [OUTPUT_NAME, 'sample_rate']):
            self.show_preview()

    def update_parameter_actuators(self, key: str):
        """A parameter changed in the settings: the virtual actuators set on it show its new value"""
        for module in self.parameter_modules():
            if module.settings[module._hw_settings_name, 'parameter'] == key:
                module.get_actuator_value()

    # ---- the waveforms
    def channel_waveforms(self) -> list[Waveform]:
        """The waveform of each channel, as set in the settings"""
        waveforms_ = []
        for group in self.settings.child('channels').children():
            cls = WaveformFactory.get_class(group['waveform'])
            waveforms_.append(cls.from_settings(group.child('parameters')))
        return waveforms_

    def load_channels(self, descriptions: list[dict]):
        """Set the waveforms of the channels from their descriptions (see :meth:`Waveform.to_dict`)

        A description beyond the channels of the target is ignored, a channel without description is left as it is.
        """
        waveforms_ = [Waveform.from_dict(description) for description in descriptions]  # all valid before any change
        groups = self.settings.child('channels').children()
        if len(waveforms_) != len(groups):
            logger.warning(f'{len(waveforms_)} waveforms for {len(groups)} channels')
        self._silent = True
        try:
            for group, waveform in zip(groups, waveforms_):
                parameters = group.child('parameters')
                if group['waveform'] != waveform.name:
                    group.child('waveform').setValue(waveform.name)
                    parameters.clearChildren()
                    parameters.addChildren(type(waveform).params())
                for name, value in waveform.to_dict().items():
                    if name != 'name':
                        parameters.child(name).setValue(value)
            self.update_parameter_choices()
        finally:
            self._silent = False
        self.show_preview()

    def sampled_waveforms(self):
        rate = self.settings[OUTPUT_NAME, 'sample_rate']
        return [waveform.to_samples(rate) for waveform in self.channel_waveforms()]

    def show_preview(self):
        """Show the channels, one viewer under the other, with the time in seconds as axis"""
        try:
            sampled = self.sampled_waveforms()
        except ValueError as e:
            logger.error(str(e))
            return
        dte = DataToExport('preview')
        for index, wave in enumerate(sampled):
            time = np.arange(len(wave.samples)) / wave.sample_rate
            label = f'Channel {index + 1}'
            if wave.frequency is not None:
                label += f' ({wave.frequency:.6g} Hz, error {wave.frequency_error:.2g} Hz)'
            dte.append(DataRaw(label, data=[wave.samples], units='V', labels=['V'],
                               axes=[Axis('time', 's', data=time)]))
        self.preview.show_data(dte)

    def send(self) -> bool:
        """Check the waveforms against the capabilities of the target and send them as its position

        Returns False (and logs why) if they cannot be sent.
        """
        module = self.target
        if module is None:
            logger.error('No waveform output actuator to send the waveforms to')
            return False
        try:
            sampled = self.sampled_waveforms()
            samples = [wave.samples for wave in sampled]
            output = WaveformOutput.from_module(module)
            output.check(samples, sample_rate=self.settings[OUTPUT_NAME, 'sample_rate'],
                         mode=self.settings[OUTPUT_NAME, 'mode'])
        except ValueError as e:
            logger.error(str(e))
            return False
        hardware = module.settings.child(module._hw_settings_name, OUTPUT_NAME)
        for name in ('sample_rate', 'mode', 'repetitions'):
            hardware.child(name).setValue(self.settings[OUTPUT_NAME, name])
        module.move_abs(DataActuator(module.title, data=samples, units='V'))
        return True

    def stop(self):
        module = self.target
        if module is not None:
            module.stop_motion()

    # ---- the virtual actuators that a scan moves
    def scannable_keys(self) -> dict[str, tuple[int, str]]:
        """The scannable parameters of the waveforms: the text of the ``parameter`` setting of the actuators, and the
        channel and the name of the parameter"""
        keys = {}
        for index, group in enumerate(self.settings.child('channels').children()):
            for name in WaveformFactory.get_class(group['waveform']).scannable_parameters():
                keys[parameter_key(index, name)] = (index, name)
        return keys

    def parameter_values(self) -> dict[str, float]:
        """The value in the settings of each scannable parameter, by the text of the ``parameter`` setting"""
        return {key: float(self.settings['channels', f'ch{channel}', 'parameters', name])
                for key, (channel, name) in self.scannable_keys().items()}

    def parameter_modules(self) -> list['DAQ_Move']:
        mods = []
        for name in self._parameter_actuators:
            module = self.dashboard.modules_manager.get_mod_from_name(name, ModuleType.Actuator)
            if module is not None:
                mods.append(module)
        return mods

    def update_parameter_choices(self):
        """Tell the virtual actuators which parameters can be scanned"""
        keys = list(self.scannable_keys())
        for module in self.parameter_modules():
            module.settings.child(module._hw_settings_name, 'parameter').setLimits(keys)

    def create_parameter_actuator(self):
        name = f'{PARAMETER_ACTUATOR} {len(self._parameter_actuators) + 1}'
        id_ = self.dashboard.modules_manager.get_random_id()
        plugin = PluginInfo(
            id=id_, name=name, class_name=PARAMETER_PLUGIN, type=ModuleType.Actuator, is_master=False,
            controller=ControllerAndThread(name=name, id=id_, is_master=False, controller=self,
                                           thread=QThreadProxy(thread=self.thread())))
        self._parameter_actuators.append(name)
        self.dashboard.module_creator.add_move_from_extension(modules=[plugin], callback=self._on_actuator_added)

    def _on_actuator_added(self, modules: list['DAQ_Move']):
        self.dashboard.module_creator.forget_callback(self._on_actuator_added)
        self.update_parameter_choices()

    def on_parameter_request(self, parameter: str, position: float):
        """A virtual actuator was moved: set the parameter, then compute and send the waveforms"""
        try:
            channel, name = self.scannable_keys()[parameter]
        except KeyError:
            logger.error(f'Unknown waveform parameter {parameter}: choose one in the actuator')
            self._answer(False)
            return
        self._silent = True  # the preview is shown once, below
        try:
            self.settings.child('channels', f'ch{channel}', 'parameters', name).setValue(position)
        finally:
            self._silent = False
        self.show_preview()  # also when the waveforms cannot be sent
        self._waiting_for_target = True
        if not self.send():
            self._waiting_for_target = False
            self._answer(False)

    def _answer(self, ok: bool):
        for module in self.parameter_modules():
            module.command_hardware.emit(ThreadCommand('waveform_loaded', ok))

    def _on_target_done(self, data):
        """The target has loaded the waveforms: finish the move of the virtual actuators waiting for it"""
        if getattr(self, '_waiting_for_target', False):
            self._waiting_for_target = False
            self._answer(True)

    def _quit_fun(self) -> bool:
        self.waveform_manager.quit_fun()
        self.waveform_manager.mainwindow.deleteLater()  # its window is never shown but it is not deleted by its quit
        if self._parameter_actuators:
            self.dashboard.remove_modules(self._parameter_actuators)
        return True


def main():
    """Start a Dashboard with the Waveform designer extension"""
    import sys
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq.dashboard import load_dashboard_with_arguments
    from pymodaq.utils.gui_utils.loader_utils import create_extension

    app = mkQApp(EXTENSION_NAME)

    win, dashboard, _ = load_dashboard_with_arguments(show_dashboard=False, load_extension=False)
    win.mainwindow.setVisible(False)
    win_ext, extension = create_extension(dashboard, WaveformDesigner, show_extension=True)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
