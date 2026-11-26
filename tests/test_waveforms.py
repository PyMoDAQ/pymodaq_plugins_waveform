"""The waveform factory: samples compared with values worked out by hand, the registry and the settings"""
from typing import ClassVar

import numpy as np
import pytest
from pymodaq_gui.parameter import Parameter

from pymodaq_data import Q_
from pymodaq_plugins_waveform import waveforms as wf
from pymodaq_plugins_waveform.waveform_factory import WaveformFactory, Waveform, waveform_field
from pymodaq_plugins_waveform.waveforms.piecewise import parse_breakpoints


def create_waveform(name, **parameters):
    return WaveformFactory().get(name, **parameters)


def test_registry_has_the_standard_forms():
    assert {'dc', 'sine', 'square', 'triangle', 'sawtooth', 'ramp', 'pulse', 'piecewise',
            'file'} <= set(WaveformFactory.names())
    assert WaveformFactory.get_class('sine') is wf.Sine and wf.Sine.name == 'sine'
    with pytest.raises(KeyError, match='Unknown waveform'):
        create_waveform('nope')


def test_a_waveform_without_name_is_refused():
    import dataclasses

    with pytest.raises(ValueError, match='no name'):
        @WaveformFactory.register()
        @dataclasses.dataclass
        class Nameless(Waveform):
            def _to_samples(self, sample_rate):
                return np.zeros(2), None


def test_a_plugin_can_register_its_own_waveform():
    import dataclasses

    @WaveformFactory.register()
    @dataclasses.dataclass
    class Constant2(Waveform):
        name: ClassVar[str] = 'test_constant2'
        value: float = waveform_field(2., 'V', 'Value')

        def _to_samples(self, sample_rate):
            return np.full(4, self.value), None

    try:
        assert Constant2.name == 'test_constant2'
        assert 'test_constant2' in WaveformFactory.names()
        assert create_waveform('test_constant2', value=Q_(3000, 'mV')).to_samples(1e3).samples.tolist() == [3.] * 4
    finally:
        WaveformFactory.unregister('test_constant2')


def test_dc():
    sampled = create_waveform('dc', level=1.5, duration=5e-3).to_samples(1000.)
    assert sampled.samples.tolist() == [1.5] * 5
    assert not sampled.periodic and sampled.frequency is None


def test_sine_one_period():
    # 800 Hz sampling, 100 Hz: 8 samples per period, the quarter of the period is the 3rd sample
    sampled = create_waveform('sine', amplitude=2., frequency=100., offset=1.).to_samples(800.)
    assert sampled.periodic and len(sampled.samples) == 8
    assert sampled.samples[0] == pytest.approx(1.)
    assert sampled.samples[2] == pytest.approx(3.)
    assert sampled.samples[4] == pytest.approx(1.)
    assert sampled.samples[6] == pytest.approx(-1.)
    assert sampled.frequency == pytest.approx(100.) and sampled.frequency_error == pytest.approx(0.)


def test_sine_phase():
    sampled = create_waveform('sine', amplitude=1., frequency=100., phase=90.).to_samples(800.)
    assert sampled.samples[0] == pytest.approx(1.)  # starts at the top


def test_frequency_is_rounded_to_a_whole_number_of_samples():
    sampled = create_waveform('sine', frequency=30.).to_samples(1000.)  # 33.3 samples per period
    assert len(sampled.samples) == 33
    assert sampled.frequency == pytest.approx(1000. / 33)
    assert sampled.frequency_error == pytest.approx(1000. / 33 - 30.)
    assert sampled.duration == pytest.approx(0.033)


def test_frequency_above_nyquist_is_refused():
    with pytest.raises(ValueError, match='half the sample rate'):
        create_waveform('sine', frequency=600.).to_samples(1000.)


def test_square():
    sampled = create_waveform('square', amplitude=2., frequency=100., offset=1., duty_cycle=0.25).to_samples(800.)
    assert sampled.samples.tolist() == [3., 3., -1., -1., -1., -1., -1., -1.]


def test_triangle():
    sampled = create_waveform('triangle', amplitude=2., frequency=100.).to_samples(800.)
    assert sampled.samples == pytest.approx([0., 1., 2., 1., 0., -1., -2., -1.])


def test_triangle_symmetry():
    # rises during a quarter of the period: starts at 0 on the rising edge, reaches the top after 1/8 of the period
    sampled = create_waveform('triangle', frequency=100., symmetry=0.25).to_samples(800.)
    assert sampled.samples.max() == pytest.approx(1.) and sampled.samples.min() == pytest.approx(-1.)
    assert sampled.samples[0] == pytest.approx(0.)
    assert int(np.argmax(sampled.samples)) == 1


def test_sawtooth():
    sampled = create_waveform('sawtooth', amplitude=4., frequency=100.).to_samples(800.)
    assert sampled.samples == pytest.approx([0., 1., 2., 3., -4., -3., -2., -1.])


def test_ramp_and_pulse():
    assert create_waveform('ramp', start=0., stop=1., duration=5e-3).to_samples(1000.).samples == \
           pytest.approx([0., 0.25, 0.5, 0.75, 1.])
    pulse = create_waveform('pulse', baseline=-1., amplitude=3., delay=2e-3, width=3e-3, duration=8e-3)
    assert pulse.to_samples(1000.).samples.tolist() == [-1., -1., 2., 2., 2., -1., -1., -1.]


def test_piecewise():
    wave = create_waveform('piecewise', points='0:0, 2e-3:4\n4e-3:4, 5e-3:0')
    assert wave.to_samples(1000.).samples == pytest.approx([0., 2., 4., 4., 4., 0.])


@pytest.mark.parametrize('text, message', [('0:0', 'two'), ('0:0, 1e-3', 'time:value'),
                                           ('0:0, 0:1', 'increase'), ('a:b, c:d', 'time:value')])
def test_breakpoints_errors(text, message):
    with pytest.raises(ValueError, match=message):
        parse_breakpoints(text)
    with pytest.raises(ValueError, match=message):
        create_waveform('piecewise', points=text)


def test_array_from_values_and_from_files(tmp_path):
    values = np.array([0., 1., 0.5])
    assert create_waveform('file', values=values).to_samples(100.).samples.tolist() == values.tolist()
    np.save(tmp_path / 'wave.npy', values)
    assert create_waveform('file', path=str(tmp_path / 'wave.npy')).to_samples(100.).samples.tolist() == values.tolist()
    (tmp_path / 'wave.csv').write_text('0\n1\n0.5\n')
    assert create_waveform('file', path=str(tmp_path / 'wave.csv')).to_samples(100.).samples.tolist() == values.tolist()
    with pytest.raises(ValueError, match='No file'):
        create_waveform('file').to_samples(100.)


def test_pint_quantities_are_converted():
    wave = create_waveform('sine', amplitude=Q_(500, 'mV'), frequency=Q_(2, 'kHz'), phase=Q_(0.5, 'turn'))
    assert (wave.amplitude, wave.frequency, wave.phase) == pytest.approx((0.5, 2000., 180.))
    assert create_waveform('sine', frequency=100.).to_samples(Q_(0.8, 'kHz')).sample_rate == 800.


def test_limits():
    with pytest.raises(ValueError, match='out of its limits'):
        create_waveform('square', duty_cycle=1.5)
    with pytest.raises(ValueError, match='positive'):
        create_waveform('dc').to_samples(0.)


@pytest.mark.parametrize('name', ['dc', 'sine', 'square', 'triangle', 'sawtooth', 'ramp', 'pulse', 'piecewise',
                                  'file'])
def test_settings_roundtrip(name):
    """The params make a settings group and the waveform is read back from it"""
    cls = WaveformFactory.get_class(name)
    group = Parameter.create(name='waveform', type='group', children=cls.params())
    wave = cls.from_settings(group)
    defaults = {f.name: f.default for f in cls._parameters()}
    assert {f.name: getattr(wave, f.name) for f in cls._parameters()} == defaults


def test_settings_carry_units_and_limits():
    params = {param['name']: param for param in wf.Square.params()}
    assert params['frequency']['suffix'] == 'Hz' and params['frequency']['siPrefix'] is True
    assert params['phase']['suffix'] == 'deg' and params['phase']['siPrefix'] is False
    assert (params['duty_cycle']['min'], params['duty_cycle']['max']) == (0., 1.)
    assert params['duty_cycle']['suffix'] == ''


def test_int_bool_and_list_parameters():
    import dataclasses

    @dataclasses.dataclass
    class Stairs(Waveform):
        name: ClassVar[str] = 'stairs'
        steps: int = waveform_field(4, title='Steps', type='int', min=1, max=100)
        reverse: bool = waveform_field(False, title='Reverse', type='bool')
        shape: str = waveform_field('linear', title='Shape', type='list', limits=['linear', 'log'])

        def _to_samples(self, sample_rate):
            return np.zeros(2), None

    params = {param['name']: param for param in Stairs.params()}
    assert [params[n]['type'] for n in ('steps', 'reverse', 'shape')] == ['int', 'bool', 'list']
    assert params['shape']['limits'] == ['linear', 'log'] and (params['steps']['min'], params['steps']['max']) == (1, 100)
    group = Parameter.create(name='waveform', type='group', children=Stairs.params())
    group['steps'], group['shape'] = 7.0, 'log'
    wave = Stairs.from_settings(group)
    assert (wave.steps, wave.reverse, wave.shape) == (7, False, 'log') and isinstance(wave.steps, int)
    with pytest.raises(ValueError, match='out of its limits'):
        Stairs(steps=0)
    with pytest.raises(ValueError, match='not one of'):
        Stairs(shape='cubic')


def test_waveform_field_refuses_inconsistent_arguments():
    with pytest.raises(ValueError, match='list parameter needs'):
        waveform_field('a', type='list')
    with pytest.raises(ValueError, match='unit is a float|with a unit'):
        waveform_field(1, 'V', type='int')
    with pytest.raises(ValueError, match='Unknown parameter type'):
        waveform_field(1, type='complex')


def test_only_the_numbers_are_scannable_by_default():
    assert WaveformFactory.get_class('sine').scannable_parameters() == ['amplitude', 'frequency', 'offset', 'phase']
    assert 'path' not in WaveformFactory.get_class('file').scannable_parameters()


def test_a_text_parameter_cannot_be_declared_scannable():
    with pytest.raises(ValueError):
        waveform_field('a', scannable=True)


def test_a_waveform_comes_back_from_its_dictionary():
    sine = WaveformFactory.create('sine', amplitude=2., frequency=500.)

    description = sine.to_dict()

    assert description['name'] == 'sine'
    assert description['frequency'] == 500.
    assert Waveform.from_dict(description) == sine
