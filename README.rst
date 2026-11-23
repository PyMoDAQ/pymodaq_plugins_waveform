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

This package holds the Dashboard extension that builds a waveform from the factory of ``pymodaq_plugins_utils``
(sine, square, triangle, ramp, pulse, piecewise linear, array...), shows it, and sends it to any actuator whose plugin
follows the waveform output contract of ``pymodaq_plugins_utils.hardware.waveform_output`` (NI-DAQmx analog outputs,
Red Pitaya...). It is under development: nothing is released yet.

This branch targets **PyMoDAQ 5.3.x** (Python 3.10 to 3.13).

Authors
=======

* Sebastien Weber
