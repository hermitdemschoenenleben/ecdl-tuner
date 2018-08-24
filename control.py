#!/usr/bin/python3
# -*- coding: utf-8 -*-
import numpy as np
from time import sleep, time
from matplotlib import pyplot as plt
from ben.devices import Meerstetter, connect_to_device_service, RedPitaya, \
    DLLException, SeperateProcess
from plumbum import colors
from utils import TemperatureOutOfBounds, replay
from lock import Lock
from config import CURRENT_LIMITS
from rough_lock import RoughLock


class FrequencyControl:
    """
    Tunes an ECDL automatically such that specific beat note frequencies
    are within the current mode.

    Usage:

        fctl = FrequencyControl(
            TBusElectronics, # electronics module
            [1e8, 1.05e8], # the desired offset frequencies
            100, # the MO current at start
            24, # the temperature at start,
            debug=True
        )

        fctl.prepare()
        fctl.do_rough_lock()
        fctl.do_lock()
        fctl.cleanup()

    This class is mainly for housekeeping.
    The algorithm is within `RoughLock`.
    """
    def __init__(self, electronics, target_frequencies, start_current,
                 start_temperature, debug=False):
        self.target_frequencies = target_frequencies
        self.start_current = start_current
        self.start_temperature = start_temperature
        self.debug = debug

        self.electronics = electronics()
        self.rough_lock = RoughLock(self)

        self._vhbg_target_temperature = self.electronics.get_vhbg_target_temperature()

    def prepare(self):
        """
        Set initial current and temperature, initialize current ramp.
        Wait for stable MIOB and VHBG temperatures.
        """
        # in case we are still in lock, turn it off
        self.electronics.unlock()

        self.vhbg_target_temperature = self.start_temperature
        self.electronics.prepare_ramp_measurement()
        self.laser_current = self.start_current

        sleep(5)

        self.electronics.wait_for_stable_temperatures()

        # quickly sweep laser current up and down
        # this ensures that for the same parameters, we always start in the same mode
        # this is not necessary for the algorithm, but good for reliability tests
        self.laser_current = CURRENT_LIMITS[0]
        sleep(.5)
        self.laser_current = self.start_current
        sleep(3)

    def do_rough_lock(self):
        """
        Perform a rough lock such that the two desired beat frequencies are within
        the current mode.
        May tune MO current and VHBG temperature.
        """
        N_temp_changes, N_wiggles = self.rough_lock.start()
        self.electronics.stop_ramp()
        return N_temp_changes, N_wiggles

    def do_lock(self):
        """
        Turn on the real lock.
        """
        def _check_lock(frequency):
            self.electronics.lock(frequency)
            sleep(1)
            _, frequencies = self.electronics.measure_frequencies(100)
            diffs = [np.abs(f - frequency) for f in frequencies]
            plt.plot(frequencies)
            plt.show()
            assert np.max(diffs) < 100e6

        _check_lock(self.target_frequencies[0])
        _check_lock(self.target_frequencies[1])
        print('lock checked')

    def cleanup(self):
        self.electronics.cleanup()
        self.rough_lock.cleanup()

        if self.debug:
            print('------------ REPLAY ------------')
            replay(self.target_frequencies, self.rough_lock.log_entries)

    @property
    def vhbg_target_temperature(self):
        return self._vhbg_target_temperature

    @vhbg_target_temperature.setter
    def vhbg_target_temperature(self, temperature):
        self.rough_lock.log(colors.dim | ('vhbg=%.2f°' % temperature))
        self.electronics.set_vhbg_target_temperature(temperature)
        self._vhbg_target_temperature = temperature

    @property
    def laser_current(self):
        return self._laser_current

    @laser_current.setter
    def laser_current(self, current):
        self.rough_lock.log(colors.dim | ('current=%.2fmA' % current))
        self.electronics.set_laser_current(current)
        self._laser_current = current


if __name__ == '__main__':
    from ben.frequency_control.electronics.ilx_rp_cnt90 import ILXRedPitayaCnt90Electronics
    from ben.frequency_control.electronics.tbus import TBusElectronics

    #target_freqs = [2.40e9, 4e9]
    target_freqs = [2.4e9, 4.4e9]

    fc = FrequencyControl(
        #ILXRedPitayaCnt90Electronics,
        TBusElectronics,
        sorted(target_freqs), 110, 25,
        debug=True
    )
    fc.prepare()

    print(colors.bold & colors.green | '== START! ==')
    t1 = time()

    try:
        fc.do_rough_lock()
    except:
        print('EXCEPTION')

    print('rough lock done, %.1f seconds!' % (time() - t1))

    #fc.do_lock()

    fc.cleanup()
