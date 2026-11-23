"""The Waveform designer extension, in an empty Dashboard with a fake waveform output actuator"""
import pytest

pytest.importorskip('pymodaq.utils.plugin_testing')

from pymodaq.utils.plugin_testing import loaded_extension

from pymodaq_plugins_waveform.extensions.waveform_designer import WaveformDesigner


def test_the_extension_loads_and_closes_without_target():
    with loaded_extension(WaveformDesigner) as (dashboard, extension):
        assert extension.settings['target'] in (None, '')
        assert [group.name() for group in extension.settings.child('channels').children()] == ['ch0']
        assert 'sine' in extension.settings.child('channels', 'ch0', 'waveform').opts['limits']


import time

import numpy as np
from qtpy import QtWidgets

from pymodaq.utils.data import DataActuator
from fake_waveform_output import DAQ_Move_FakeWaveformOutput, register, make_module
from pymodaq_plugins_waveform.daq_move_plugins.daq_move_WaveformParameter import DAQ_Move_WaveformParameter


def wait_for(condition, timeout=5.):
    t0 = time.time()
    while not condition() and time.time() - t0 < timeout:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)
    return condition()


@pytest.fixture
def designer():
    register('FakeWaveformOutput', DAQ_Move_FakeWaveformOutput)
    register('WaveformParameter', DAQ_Move_WaveformParameter)
    with loaded_extension(WaveformDesigner) as (dashboard, extension):
        output = make_module('FakeWaveformOutput', 'ao')
        dashboard.modules_manager.add_modules([output])
        extension.refresh_targets()
        yield extension, output
        output.quit_fun()


def test_the_channels_of_the_target_become_groups_of_settings(designer):
    extension, output = designer

    assert extension.settings['target'] == 'ao'
    assert [group.name() for group in extension.settings.child('channels').children()] == ['ch0', 'ch1']


def test_sending_loads_the_waveforms_in_the_target(designer):
    extension, output = designer
    extension.settings.child('channels', 'ch1', 'waveform').setValue('dc')

    done = []
    output.move_done_signal.connect(done.append)

    assert extension.send()

    assert wait_for(lambda: done)
    sine, dc = done[0].data
    assert 0.9 < np.max(sine) <= 1.  # the sine of amplitude 1 V
    assert np.allclose(dc, dc[0])  # the DC of the other channel


def test_a_waveform_that_exceeds_the_target_is_not_sent(designer, caplog):
    extension, output = designer
    extension.settings.child('channels', 'ch0', 'parameters', 'amplitude').setValue(50.)

    assert not extension.send()


def test_the_parameters_to_scan_are_listed_by_the_waveforms(designer):
    extension, output = designer

    keys = extension.scannable_keys()

    assert keys['Channel 1: frequency'] == (0, 'frequency')
    assert 'Channel 2: amplitude' in keys


def test_moving_a_parameter_actuator_loads_the_waveform_and_ends_the_move(designer):
    extension, output = designer
    extension.create_parameter_actuator()
    assert wait_for(lambda: extension.parameter_modules())
    (actuator,) = extension.parameter_modules()
    assert wait_for(lambda: 'Channel 1: amplitude' in actuator.settings.child(
        actuator._hw_settings_name, 'parameter').opts['limits'])
    actuator.settings.child(actuator._hw_settings_name, 'parameter').setValue('Channel 1: amplitude')
    done, loaded = [], []
    actuator.move_done_signal.connect(done.append)
    output.move_done_signal.connect(loaded.append)

    actuator.move_abs(DataActuator('amplitude', data=3.))

    assert wait_for(lambda: done and loaded)
    assert extension.settings['channels', 'ch0', 'parameters', 'amplitude'] == 3.
    assert 2.5 < np.max(loaded[0].data[0]) <= 3.


def test_an_actuator_added_to_the_dashboard_becomes_a_target(designer):
    extension, output = designer
    other = make_module('FakeWaveformOutput', 'ao2')
    try:
        extension.dashboard.modules_manager.add_modules([other])

        assert set(extension.settings.child('target').opts['limits']) == {'ao', 'ao2'}
    finally:
        other.quit_fun()


def test_without_target_a_waveform_can_be_previewed_but_not_sent():
    with loaded_extension(WaveformDesigner) as (dashboard, extension):
        extension.settings.child('channels', 'ch0', 'waveform').setValue('square')

        extension.show_preview()

        assert not extension.send()


def test_the_preview_follows_the_changes_of_the_settings(designer, monkeypatch):
    extension, output = designer
    previews = []
    monkeypatch.setattr(extension, 'show_preview', lambda: previews.append(1))

    extension.settings.child('channels', 'ch0', 'parameters', 'amplitude').setValue(2.)
    assert len(previews) == 1

    extension.settings.child('channels', 'ch1', 'waveform').setValue('square')
    assert len(previews) == 2  # once for the new waveform, not for each of its parameters

    extension.settings.child('waveform_output', 'sample_rate').setValue(2e4)
    assert len(previews) == 3


def test_the_repetitions_are_shown_for_the_repeat_mode_only(designer):
    extension, output = designer
    repetitions = extension.settings.child('waveform_output', 'repetitions')

    assert not repetitions.opts['visible']

    extension.settings.child('waveform_output', 'mode').setValue('repeat')
    assert repetitions.opts['visible']

    extension.settings.child('waveform_output', 'mode').setValue('finite')
    assert not repetitions.opts['visible']


def test_the_waveforms_are_saved_and_loaded_by_name(designer, tmp_path, monkeypatch):
    extension = designer[0]
    manager = extension.waveform_manager
    monkeypatch.setattr(type(manager), 'get_entry_folder', lambda self, **kw: tmp_path)
    extension.settings.child('channels', 'ch0', 'parameters', 'frequency').setValue(7.)
    manager.create_entry('seven', bypass_dialog=True)
    extension.settings.child('channels', 'ch0', 'parameters', 'frequency').setValue(3.)

    manager.execute_entry('seven')

    assert extension.settings['channels', 'ch0', 'parameters', 'frequency'] == 7.
    assert (tmp_path / 'seven.toml').is_file()


def test_a_file_of_an_unknown_version_is_refused(designer, tmp_path, monkeypatch):
    extension = designer[0]
    manager = extension.waveform_manager
    monkeypatch.setattr(type(manager), 'get_entry_folder', lambda self, **kw: tmp_path)
    (tmp_path / 'future.toml').write_text('version = 99\nchannels = []\n')

    with pytest.raises(ValueError):
        manager.read_entry(tmp_path / 'future.toml')


def test_a_parameter_actuator_reads_and_sets_the_value_of_the_extension(designer):
    extension, output = designer
    extension.create_parameter_actuator()
    assert wait_for(lambda: extension.parameter_modules())
    (actuator,) = extension.parameter_modules()
    assert wait_for(lambda: 'Channel 1: amplitude' in actuator.settings.child(
        actuator._hw_settings_name, 'parameter').opts['limits'])
    actuator.settings.child(actuator._hw_settings_name, 'parameter').setValue('Channel 1: amplitude')
    extension.settings.child('channels', 'ch0', 'parameters', 'amplitude').setValue(2.)
    actuator.get_actuator_value()
    assert wait_for(lambda: actuator._current_value.value() == 2.)  # not current_value: it recurses when the origin is empty
    done = []
    actuator.move_done_signal.connect(done.append)

    actuator.move_abs(DataActuator('amplitude', data=0.))

    assert wait_for(lambda: done)
    assert extension.settings['channels', 'ch0', 'parameters', 'amplitude'] == 0.
    assert extension.parameter_values()['Channel 1: amplitude'] == 0.


def test_the_toolbar_of_the_manager_is_in_the_window_of_the_extension(designer):
    extension, _ = designer
    toolbar = extension.get_toolbar('waveform_manager')

    assert toolbar in extension.get_app_toolbars()
    assert len(toolbar.actions()) >= 7  # the entries, execute, new, copy, save, reload, delete
