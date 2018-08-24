from ben.devices import connect_to_device_service, RedPitaya, SeperateProcess, Meerstetter
import numpy as np
from time import time, sleep
from ben.frequency_control.config import RAMP_FREQUENCY, RAMP_AMPLITUDE, DECIMATION_FACTOR, \
    FREQ_MEASUREMENT_TIME, FREQ_MEASUREMENT_RATE, SKIP_POINTS, \
    CURRENT_MOD_FACTOR
from ben.frequency_control.utils import find_negative_ramp, wait_for_stable_temperature


class ILXRedPitayaCnt90Electronics:
    _ramp_started = False

    def __init__(self):
        self.ilx = connect_to_device_service('192.168.1.177', 'ilx')
        self.redpitaya = RedPitaya('rp-f012ba.local')
        self.ramp_out = self.redpitaya.fast_out[1]
        self.trigger_out = self.redpitaya.fast_out[0]
        self.counter = connect_to_device_service('192.168.1.177', 'cnt90')
        self.vhbg = Meerstetter.by_address(1)
        self.miob = SeperateProcess(lambda: Meerstetter.by_address(2))

        self._coarse_temp_ramp = self.vhbg.parameters['COARSE_TEMP_RAMP']
        self._proximity_width = self.vhbg.parameters['PROXIMITY_WIDTH']

        self.vhbg.parameters['COARSE_TEMP_RAMP'] = 1.5
        self.vhbg.parameters['PROXIMITY_WIDTH'] = 0
    
    def get_vhbg_temperature(self):
        return self.vhbg.get_temperature()
    
    def get_vhbg_target_temperature(self):
        return self.vhbg.parameters['TARGET_OBJECT_TEMPERATURE']
    
    def set_vhbg_target_temperature(self, temperature):
        self.vhbg.set_target_temperature(temperature)
    
    def wait_for_stable_temperatures(self):
        print('warte auf stabile VHBG-Temperatur')
        wait_for_stable_temperature(self.vhbg, 0.005)
        print('warte auf stabile MIOB-Temperatur')
        wait_for_stable_temperature(self.miob, 0.001)

    def set_laser_current(self, current):
        self.ilx.root.set_laser_current(current)

    def prepare_ramp_measurement(self):
        if not self._ramp_started:
            self._ramp_started = True
            # start ramp
            self.ramp_out.enabled = False
            self.ramp_out.frequency = RAMP_FREQUENCY
            self.ramp_out.offset = 0
            self.ramp_out.amplitude = RAMP_AMPLITUDE
            self.ramp_out.wave_form = 'TRIANGLE'
            self.ramp_out.enabled = True

            self._set_trigger(False)

            sleep(0.1)

        self.redpitaya.set_acquisition_trigger(
            'CH2_PE', decimation=DECIMATION_FACTOR, delay=8192 + 900
        )
        self.counter.root.frequency_measurement(
            'C', FREQ_MEASUREMENT_TIME, FREQ_MEASUREMENT_RATE, 'REAR',
            wait=False
        )

    def stop_ramp(self):
        # stop ramp
        self.ramp_out.enabled = False

    def _set_trigger(self, value):
        self.trigger_out.set_constant_voltage(1 if value else 0)

    def measure_frequencies(self, center_current):
        t1 = time()
        ramp_in = self.redpitaya.fast_in[0]

        self._set_trigger(True)

        while not self.redpitaya.was_triggered():
            print('not triggered')
            sleep(0.01)

        ramp = ramp_in.read_buffer()[::SKIP_POINTS]
        frequencies = list(self.counter.root.wait_and_return())

        """from matplotlib import pyplot as plt
        plt.plot(ramp)
        plt.show()
        plt.plot(frequencies)
        plt.show()"""

        # do this after data acquiry because it causes a crosstalk on the other
        # redpitaya channel
        self._set_trigger(False)

        slice_ = find_negative_ramp(ramp)
        # offset corrects a delay between redpitaya and counter triggering
        offset = 0
        frequencies = np.array(frequencies[
            slice(slice_.start + offset, slice_.stop + offset, slice_.step)
        ])
        currents = np.array(ramp[slice_]) * CURRENT_MOD_FACTOR + \
            center_current

        """print('SHIFTED')
        plt.plot(currents)
        plt.show()
        plt.plot(frequencies)
        plt.show()"""

        return currents, frequencies

    def cleanup(self):
        self._set_trigger(True)
        sleep(0.5)
        self._set_trigger(False)
        self.miob.close()
        self.vhbg.parameters['COARSE_TEMP_RAMP'] = self._coarse_temp_ramp
        self.vhbg.parameters['PROXIMITY_WIDTH'] = self._proximity_width