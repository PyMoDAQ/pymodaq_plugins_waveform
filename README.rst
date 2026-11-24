pymodaq_plugins_waveform
########################


.. image:: https://img.shields.io/pypi/v/pymodaq_plugins_waveform.svg
   :target: https://pypi.org/project/pymodaq_plugins_waveform/
   :alt: Latest Version

.. image:: https://readthedocs.org/projects/pymodaq/badge/?version=latest
   :target: https://pymodaq.readthedocs.io/en/stable/?badge=latest
   :alt: Documentation Status

.. image:: https://github.com/PyMoDAQ/pymodaq_plugins_waveform/workflows/Upload%20Python%20Package/badge.svg
   :target: https://github.com/PyMoDAQ/pymodaq_plugins_waveform
   :alt: Publication Status

.. image:: https://github.com/PyMoDAQ/pymodaq_plugins_waveform/actions/workflows/Test.yml/badge.svg
    :target: https://github.com/PyMoDAQ/pymodaq_plugins_waveform/actions/workflows/Test.yml


Design waveforms and send them to the analog outputs and arbitrary waveform generators of the Dashboard.

Authors
=======

* Sebastien Weber

Instruments
===========

Actuators
+++++++++

* **WaveformParameter**: virtual actuator, created by the Waveform designer extension, that a scan moves to change one
  parameter of a waveform.

Extensions
++++++++++

* **Waveform designer**: builds one waveform per channel, shows them, and sends them to any actuator whose plugin
  follows the waveform output contract of ``pymodaq_plugins_utils.hardware.waveform_output`` (NI-DAQmx analog outputs,
  Red Pitaya...). Sets of waveforms can be saved by name.

The package also holds the factory of waveforms (sine, square, triangle, ramp, pulse, piecewise linear, file...).
It is under development: nothing is released yet.

Requirements
============

This package needs **PyMoDAQ 5.4** (``pymodaq``, ``pymodaq_gui``, ``pymodaq_data`` ``>=5.4.0a0``) and Python 3.11 to
3.14: the virtual actuator relies on ``move_failed_signal`` of the actuator modules, only in PyMoDAQ 5.4. Until 5.4.0 is
released, install the alpha (``pip install --pre pymodaq``).
