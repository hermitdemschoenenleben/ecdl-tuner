import numpy as np
from ben.control.client import DeviceClient
from ben.frequency_control.utils import wait_for_stable_temperature

RAMP_CURRENT_SPAN = 15 # mA
PRESCALER = 10

class TBusElectronics:
    def __init__(self):
        self.server = DeviceClient('control')
        self.server.pause_background_services()
        self.ramper = DeviceClient('ramper')
        self.freq_ctl = self.ramper.card
        self.ecdl = DeviceClient('ecdl')
        self.ramp_channel = 2
        self.counter_channel = 0
        self.vhbg = DeviceClient('vhbg')
        self.miob = DeviceClient('miob')

        self._ramp_started = False

        self._coarse_temp_ramp = self.vhbg.get_parameter('COARSE_TEMP_RAMP')
        self._proximity_width = self.vhbg.get_parameter('PROXIMITY_WIDTH')

        self.vhbg.set_parameter('COARSE_TEMP_RAMP', .8)
        self.vhbg.set_parameter('PROXIMITY_WIDTH', 0)

        self.freq_ctl.set_gate_time(10e-6)
        # the photodiode can't see frequencies > 7GHz anyway
        # divider 8 allows to see frequencies up to 800MHz, with prescaler 10 this is 8GHz
        self.freq_ctl.set_beat_divider2_enabled(self.counter_channel, False)
        self.freq_ctl.set_beat_divider(self.counter_channel, 8)
        self.freq_ctl.apply_registers()

    def get_vhbg_temperature(self):
        print('messung vhbg')
        return self.vhbg.get_temperature()

    def get_vhbg_target_temperature(self):
        return self.vhbg.get_parameter('TARGET_OBJECT_TEMPERATURE')

    def set_vhbg_target_temperature(self, temperature):
        self.vhbg.set_target_temperature(temperature)

    def wait_for_stable_temperatures(self):
        print('warte auf stabile VHBG-Temperatur')
        wait_for_stable_temperature(self.vhbg, 0.005)
        print('warte auf stabile MIOB-Temperatur')
        wait_for_stable_temperature(self.miob, 0.001)

    def set_laser_current(self, value):
        self.ecdl.set_mo_current(value)

    def prepare_ramp_measurement(self):
        # TODO: only if necessary
        if not self._ramp_started:
            self.ramper.start_ramp(self.ramp_channel, 1, 10)
            self._ramp_started = True

    def stop_ramp(self):
        self.ramper.stop_ramp(self.ramp_channel)
        self._ramp_started = False

    def measure_frequencies(self, center_current):
        from time import time
        t1 = time()
        addresses = list([i+512 for i in range(512)][::4])
        frequencies = self.ramper.measure_frequencies(
            self.counter_channel,
            addresses=addresses
        )
        frequencies = list(reversed(list(frequencies)))
        frequencies = [f * PRESCALER for f in frequencies]

        # we have a prescaler with factor 10 in beat detection
        #frequencies = [f*10 for f in frequencies]
        currents = center_current + \
            np.linspace(-RAMP_CURRENT_SPAN/2, RAMP_CURRENT_SPAN/2, len(addresses))

        print('counter read time', time() - t1)
        """from matplotlib import pyplot as plt
        plt.plot(currents, frequencies)
        plt.show()"""

        return currents, frequencies

    def cleanup(self):
        self.vhbg.set_parameter('COARSE_TEMP_RAMP', self._coarse_temp_ramp)
        self.vhbg.set_parameter('PROXIMITY_WIDTH', self._proximity_width)
        self.server.continue_background_services()

    def lock(self, setpoint):
        setpoint /= PRESCALER
        self.freq_ctl.set_and_apply_pid_setpoints(
            0,
            [setpoint, setpoint, setpoint],
            [False, False, False],
        )
        self.freq_ctl.set_and_apply_pid_factors(3, -1, -1)
        self.freq_ctl.set_pid_signal_source(3, 0)
        self.freq_ctl.set_pid_address(0)
        self.freq_ctl.set_channel_mode_fast(
            self.ramp_channel, int(self.freq_ctl.OUTPUT_MODES.offset_pid)
        )
        self.freq_ctl.apply_registers()

    def unlock(self):
        """
        Turn off the lock.
        """
        self.freq_ctl.set_channel_mode_fast(
            3, int(self.freq_ctl.OUTPUT_MODES.offset)
        )
        self.freq_ctl.apply_registers()
