import numpy as np
from time import time, sleep
from control import FrequencyControl
from ben.frequency_control.electronics.ilx_rp_cnt90 import ILXRedPitayaCnt90Electronics
from ben.frequency_control.electronics.tbus import TBusElectronics
from utils import TemperatureOutOfBounds, NoSlope, NotReachable
import pickle
from traceback import print_exc

DATA_FOLDER = '../../data/frequency_control/'

NO_SLOPE = -1
TEMPERATURE_OUT_OF_BOUNDS = -2
NOT_REACHABLE = -3
LOCK_FAILED = -4


def test_control():
    N_currents = 25
    N_temperatures = 1

    currents = np.linspace(100, 125, N_currents)
    #temperatures = np.linspace(22.3, 27.5, N_temperatures)
    min_temp = 23.6155172
    max_temp = 23.6155172
    mean_temp = np.mean([min_temp, max_temp])
    temperatures = np.linspace(min_temp, max_temp, N_temperatures)
    #temperatures = np.linspace(23.8, 24.2, N_temperatures)

    temperatures_and_idxs = list(enumerate(temperatures))
    temperatures_and_idxs = sorted(
        temperatures_and_idxs,
        key=lambda idx_and_temp: np.abs(mean_temp - idx_and_temp[1])
    )

    """with open(DATA_FOLDER + 'data.pickle', 'rb') as f:
        old_data = pickle.load(f)
        data = old_data['data']
        vhbg_end = old_data['vhbg_end']
        vhbg_change = old_data['vhbg_change']
        max_miob_diffs = old_data['max_miob_diffs']
        N_wiggles_matrix = old_data['N_wiggles']
        N_temp_changes_matrix = old_data['N_temp_changes']"""

    data = np.zeros((N_temperatures, N_currents))
    max_miob_diffs = np.zeros((N_temperatures, N_currents))
    vhbg_change = np.zeros((N_temperatures, N_currents))
    vhbg_end = np.zeros((N_temperatures, N_currents))
    N_wiggles_matrix = np.zeros((N_temperatures, N_currents))
    N_temp_changes_matrix = np.zeros((N_temperatures, N_currents))

    def write_data():
        f = open(DATA_FOLDER + 'data.pickle', 'wb')
        pickle.dump({
            'vhbg_end': vhbg_end,
            'vhbg_change': vhbg_change,
            'max_miob_diffs': max_miob_diffs,
            'data': data,
            'currents': currents,
            'temperatures': temperatures,
            'N_wiggles': N_wiggles_matrix,
            'N_temp_changes': N_temp_changes_matrix
        }, f)
        f.close()

    try:
        for j, temp in temperatures_and_idxs:
            print('TEMPERATURE', j, temp)
            for i, current in enumerate(currents):
                print('RUN, i=', i, 'j=', j)
                if data[j, i] != 0:
                    print('skip')
                    continue

                try:
                    fc = FrequencyControl(
                        TBusElectronics,
                        [2.4e9, 4e9], current, temp
                    )
                    target_temp = fc.electronics.miob.get_target_temperature()

                    fc.prepare()
                    t1 = time()
                    N_temp_changes, N_wiggles = fc.do_rough_lock()
                except NoSlope:
                    duration = NO_SLOPE
                except TemperatureOutOfBounds:
                    duration = TEMPERATURE_OUT_OF_BOUNDS
                except NotReachable:
                    duration = NOT_REACHABLE
                else:
                    duration = time() - t1
                    N_wiggles_matrix[j, i] = N_wiggles
                    N_temp_changes_matrix[j, i] = N_temp_changes

                print('duration', duration)

                max_miob_diff = 0

                for _ in range(10):
                    miob_temp = fc.electronics.miob.get_temperature()
                    temp_diff = np.abs(miob_temp - target_temp)
                    if temp_diff > max_miob_diff:
                        max_miob_diff = temp_diff

                    sleep(1)

                """if duration > 0:
                    try:
                        fc.do_lock()
                    except:
                        duration = LOCK_FAILED"""

                data[j, i] = duration
                max_miob_diffs[j, i] = max_miob_diff
                v = fc.electronics.vhbg.get_temperature()
                vhbg_end[j, i] = v
                vhbg_change[j, i] = np.abs(temp - v)

                try:
                    fc.cleanup()
                except:
                    pass

                write_data()

    except Exception as e:
        print('EXC')
        print_exc()

    try:
        fc.electronics.vhbg.set_target_temperature(24)
    except:
        pass

    print(data)
    #data = np.array(d)
    #data[data == TEMPERATURE_OUT_OF_BOUNDS] = 1000
    #print(data)

    return data


if __name__ == '__main__':
    d = test_control()
